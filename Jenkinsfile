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
