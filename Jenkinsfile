pipeline {
    agent any
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
                    BEFORE=${GIT_PREVIOUS_SUCCESSFUL_COMMIT:-}
                    if [ -z "$BEFORE" ]; then
                      BEFORE=$(git rev-list --max-parents=0 HEAD)
                    fi
                    python3 scripts/gitops_reconcile.py --before "$BEFORE" --after "$AFTER" --mode "$GITOPS_MULTI_DEPLOYMENT_MODE"
                '''
            }
        }
    }
    post {
        always { archiveArtifacts artifacts: 'logs/**', allowEmptyArchive: true }
    }
}
