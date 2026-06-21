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
        CFY_MANAGER_URL = credentials('cfy-manager-url')
        CFY_USERNAME = credentials('cfy-username')
        CFY_PASSWORD = credentials('cfy-password')
        CFY_TENANT = credentials('cfy-tenant')
        CFY_API_VERSION = 'v3.1'
        CFY_INSECURE = 'true'
        GITOPS_MULTI_DEPLOYMENT_MODE = 'all'
    }
    stages {
        stage('Checkout') {
            steps { checkout scm }
        }
        stage('Install dependencies') {
            steps {
                sh 'python3 -m pip install -r requirements.txt --break-system-packages || python3 -m pip install -r requirements.txt'
                sh 'python3 -m pip install ruff yamllint pip-audit --break-system-packages || python3 -m pip install ruff yamllint pip-audit'
            }
        }
        stage('Code Quality & Static Analysis') {
            parallel {
                stage('Python Lint') {
                    steps {
                        sh 'python3 -m ruff check scripts/ --output-format=text'
                    }
                }
                stage('YAML Validation') {
                    steps {
                        sh 'yamllint -d "{extends: relaxed, rules: {line-length: disable, trailing-spaces: {level: warning}, empty-lines: {level: warning}}}" deployments/ operations/ inputs/ workflow-params/'
                    }
                }
                stage('Shell Lint') {
                    steps {
                        sh 'shellcheck run-local.sh reset-jenkins-e2e.sh cleanup-jenkins-e2e.sh run-jenkins-e2e.sh || true'
                    }
                }
            }
        }
        stage('Security Checks') {
            parallel {
                stage('Dependency Audit') {
                    steps {
                        sh 'pip-audit -r requirements.txt || true'
                    }
                }
                stage('Secrets Scan') {
                    steps {
                        sh '''
                            echo "Scanning for hardcoded secrets..."
                            if grep -rn "password\\|secret\\|token\\|api_key" scripts/ --include="*.py" | grep -v "password=" | grep -v "#" | grep -v "CFY_PASSWORD" | grep -v "def \\|args\\|environ\\|getenv\\|credentials"; then
                                echo "WARNING: Potential secrets found in code"
                            else
                                echo "PASS: No hardcoded secrets detected"
                            fi
                        '''
                    }
                }
            }
        }
        stage('Smoke Test - Conductor API') {
            steps {
                sh '''
                    set -e
                    echo "Testing Conductor API connectivity..."
                    HTTP_CODE=$(curl -s -o /tmp/cfy-status.json -w "%{http_code}" -u "$CFY_USERNAME:$CFY_PASSWORD" -H "Tenant: $CFY_TENANT" "$CFY_MANAGER_URL/api/$CFY_API_VERSION/status" --insecure --connect-timeout 10)
                    if [ "$HTTP_CODE" = "200" ]; then
                        echo "PASS: Conductor API reachable (HTTP $HTTP_CODE)"
                        cat /tmp/cfy-status.json | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Status: {d[\"status\"]}')"
                    else
                        echo "FAIL: Conductor API returned HTTP $HTTP_CODE"
                        exit 1
                    fi
                '''
            }
        }
        stage('Reconcile Cloudify envops changes') {
            steps {
                sh '''
                    set -e
                    AFTER=$(git rev-parse HEAD)
                    STATE_FILE="$WORKSPACE/.last_reconciled_sha"

                    if [ ! -f "$STATE_FILE" ]; then
                      echo "$AFTER" > "$STATE_FILE"
                      echo "Initial Jenkins baseline captured at $AFTER. No Cloudify action is taken on first run."
                      echo "Push a new commit under deployments/ or operations/ to trigger reconciliation."
                      exit 0
                    fi

                    BEFORE=$(cat "$STATE_FILE")
                    if [ "$BEFORE" = "$AFTER" ]; then
                      echo "No new commit since last reconciliation: $AFTER"
                      exit 0
                    fi

                    echo "Reconciling Cloudify envops from $BEFORE to $AFTER"
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
