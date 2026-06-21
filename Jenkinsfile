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
                sh 'python3 -m pip install ruff yamllint pip-audit --break-system-packages 2>/dev/null || true'
            }
        }
        stage('Code Quality') {
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    sh '''
                        echo "=== Python Lint ==="
                        python3 -m ruff check scripts/ --output-format=text
                        echo "=== YAML Validation ==="
                        yamllint -d "{extends: relaxed, rules: {line-length: disable, trailing-spaces: {level: warning}, empty-lines: {level: warning}}}" deployments/ operations/ inputs/ workflow-params/
                    '''
                }
            }
        }
        stage('Security Checks') {
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    sh '''
                        echo "=== Dependency Audit ==="
                        pip-audit -r requirements.txt
                        echo "=== Secrets Scan ==="
                        if grep -rnE "password|secret|token" scripts/ --include="*.py" | grep -v "password=" | grep -v "#" | grep -vE "def |args|environ|getenv|credentials"; then
                            echo "WARNING: Potential secrets found"
                            exit 1
                        else
                            echo "PASS: No hardcoded secrets"
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
