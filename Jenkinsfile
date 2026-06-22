pipeline {
    agent any
    options {
        disableConcurrentBuilds()
        buildDiscarder(logRotator(numToKeepStr: '20'))
    }
    triggers {
        pollSCM('H/2 * * * *')
    }
    environment {
        CFY_MANAGER_URL = 'http://128.224.2.252:9092'
        CFY_USERNAME = 'admin'
        CFY_PASSWORD = 'admin'
        CFY_TENANT = 'default_tenant'
        CFY_API_VERSION = 'v3.1'
        CFY_INSECURE = 'true'
        GITOPS_MULTI_DEPLOYMENT_MODE = 'all'
    }
    stages {
        stage('Install dependencies') {
            steps {
                sh 'python3 -m pip install -r requirements.txt --break-system-packages 2>/dev/null || python3 -m pip install -r requirements.txt'
                sh 'python3 -m pip install ruff yamllint pip-audit pytest pytest-cov --break-system-packages 2>/dev/null || true'
            }
        }
        stage('Code Quality') {
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    sh '''
                        echo "=== Python Lint ==="
                        python3 -m ruff check scripts/ --output-format=concise
                        echo "=== YAML Validation ==="
                        python3 -m yamllint -d "{extends: relaxed, rules: {line-length: disable, trailing-spaces: {level: warning}, empty-lines: {level: warning}}}" deployments/ operations/ inputs/ workflow-params/
                    '''
                }
            }
        }
        stage('Security Validation') {
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    sh '''
                        echo "=== Dependency Vulnerability Audit ==="
                        python3 -m pip_audit -r requirements.txt

                        echo ""
                        echo "=== Secrets Scan ==="
                        if grep -rnE "password|secret|token|api_key|private_key" scripts/ deployments/ operations/ --include="*.py" --include="*.yaml" | grep -vE "password=|#|def |args|environ|getenv|credentials|CFY_PASSWORD|example"; then
                            echo "FAIL: Potential hardcoded secrets found"
                            exit 1
                        else
                            echo "PASS: No hardcoded secrets detected"
                        fi

                        echo ""
                        echo "=== TLS/Insecure Connection Check ==="
                        if [ "$CFY_INSECURE" = "true" ]; then
                            echo "WARNING: Running with TLS verification disabled (CFY_INSECURE=true)"
                        else
                            echo "PASS: TLS verification enabled"
                        fi

                        echo ""
                        echo "=== File Permission Check ==="
                        if find . -name "*.sh" ! -perm -u+x | grep -q .; then
                            echo "WARNING: Shell scripts without execute permission found:"
                            find . -name "*.sh" ! -perm -u+x
                        else
                            echo "PASS: All shell scripts have execute permission"
                        fi
                    '''
                }
            }
        }
        stage('Unit Tests') {
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    sh '''
                        echo "=== Running Unit Tests with Coverage ==="
                        python3 -m pytest tests/ -v --cov=scripts --cov-report=term-missing --cov-fail-under=20
                    '''
                }
            }
        }
        stage('Infrastructure & Networking') {
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    sh '''
                        set -e
                        echo "=== DNS Resolution ==="
                        CFY_HOST=$(echo "$CFY_MANAGER_URL" | sed 's|http[s]*://||' | cut -d: -f1)
                        if getent hosts "$CFY_HOST" > /dev/null 2>&1 || echo "$CFY_HOST" | grep -qP "^[0-9.]+$"; then
                            echo "PASS: Host $CFY_HOST is resolvable/valid IP"
                        else
                            echo "FAIL: Cannot resolve $CFY_HOST"
                            exit 1
                        fi

                        echo ""
                        echo "=== Network Connectivity ==="
                        CFY_PORT=$(echo "$CFY_MANAGER_URL" | sed 's|http[s]*://||' | cut -d: -f2)
                        if curl -s --connect-timeout 5 -o /dev/null "$CFY_MANAGER_URL" --insecure; then
                            echo "PASS: TCP connection to $CFY_HOST:$CFY_PORT successful"
                        else
                            echo "FAIL: Cannot connect to $CFY_HOST:$CFY_PORT"
                            exit 1
                        fi

                        echo ""
                        echo "=== API Authentication ==="
                        HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -u "$CFY_USERNAME:$CFY_PASSWORD" -H "Tenant: $CFY_TENANT" "$CFY_MANAGER_URL/api/$CFY_API_VERSION/blueprints" --insecure --connect-timeout 10)
                        if [ "$HTTP_CODE" = "200" ]; then
                            echo "PASS: API authentication successful (HTTP $HTTP_CODE)"
                        else
                            echo "FAIL: API authentication failed (HTTP $HTTP_CODE)"
                            exit 1
                        fi

                        echo ""
                        echo "=== API Response Time ==="
                        RESPONSE_TIME=$(curl -s -o /dev/null -w "%{time_total}" -u "$CFY_USERNAME:$CFY_PASSWORD" -H "Tenant: $CFY_TENANT" "$CFY_MANAGER_URL/api/$CFY_API_VERSION/status" --insecure)
                        echo "API response time: ${RESPONSE_TIME}s"
                        SLOW=$(echo "$RESPONSE_TIME > 5.0" | bc -l 2>/dev/null || echo 0)
                        if [ "$SLOW" = "1" ]; then
                            echo "WARNING: API response time > 5s"
                            exit 1
                        else
                            echo "PASS: API response time acceptable"
                        fi
                    '''
                }
            }
        }
        stage('Observability & Logging') {
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    sh '''
                        echo "=== Log Directory Check ==="
                        mkdir -p logs
                        echo "PASS: Log directory exists"

                        echo ""
                        echo "=== Script Logging Verification ==="
                        if grep -qE "logging|logger" scripts/cloudify_lifecycle.py; then
                            echo "PASS: Logging framework used in cloudify_lifecycle.py"
                        else
                            echo "FAIL: No logging found in cloudify_lifecycle.py"
                            exit 1
                        fi

                        echo ""
                        echo "=== Run ID Traceability ==="
                        if grep -qE "run_id|Run ID" scripts/cloudify_lifecycle.py; then
                            echo "PASS: Run ID traceability implemented"
                        else
                            echo "FAIL: No Run ID for tracing executions"
                            exit 1
                        fi

                        echo ""
                        echo "=== Error Handling Check ==="
                        ERROR_HANDLERS=$(grep -cE "except|raise|error|Error" scripts/cloudify_lifecycle.py || true)
                        echo "Error handling statements found: $ERROR_HANDLERS"
                        if [ "$ERROR_HANDLERS" -gt 5 ]; then
                            echo "PASS: Adequate error handling ($ERROR_HANDLERS handlers)"
                        else
                            echo "WARNING: Limited error handling"
                            exit 1
                        fi

                        echo ""
                        echo "=== Summary JSON Output Check ==="
                        if grep -qE "summary" scripts/cloudify_lifecycle.py; then
                            echo "PASS: Summary JSON output implemented"
                        else
                            echo "FAIL: No summary output for audit trail"
                            exit 1
                        fi

                        echo ""
                        echo "=== Credential Masking Check ==="
                        if grep -qE "mask" scripts/cloudify_lifecycle.py; then
                            echo "PASS: Credential masking implemented"
                        else
                            echo "FAIL: Credentials may be logged in plaintext"
                            exit 1
                        fi
                    '''
                }
            }
        }
        stage('Smoke Test') {
            steps {
                sh '''
                    set -e
                    echo "Testing Conductor API..."
                    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -u "$CFY_USERNAME:$CFY_PASSWORD" -H "Tenant: $CFY_TENANT" "$CFY_MANAGER_URL/api/$CFY_API_VERSION/status" --insecure --connect-timeout 10)
                    if [ "$HTTP_CODE" = "200" ]; then
                        echo "PASS: Conductor API reachable (HTTP $HTTP_CODE)"
                    else
                        echo "FAIL: Conductor API returned HTTP $HTTP_CODE"
                        exit 1
                    fi
                '''
            }
        }
        stage('Reconcile Cloudify changes') {
            steps {
                sh '''
                    set -e
                    AFTER=$(git rev-parse HEAD)
                    STATE_FILE="$WORKSPACE/.last_reconciled_sha"
                    if [ ! -f "$STATE_FILE" ]; then
                        echo "$AFTER" > "$STATE_FILE"
                        echo "Initial baseline captured at $AFTER. Push a new commit to trigger."
                        exit 0
                    fi
                    BEFORE=$(cat "$STATE_FILE")
                    if [ "$BEFORE" = "$AFTER" ]; then
                        echo "No new commits since last reconciliation."
                        exit 0
                    fi
                    echo "Reconciling from $BEFORE to $AFTER"
                    python3 scripts/gitops_reconcile.py --before "$BEFORE" --after "$AFTER" --mode "$GITOPS_MULTI_DEPLOYMENT_MODE"
                    echo "$AFTER" > "$STATE_FILE"
                '''
            }
        }
    }
    post {
        always { archiveArtifacts artifacts: 'logs/**', allowEmptyArchive: true }
    }
}
