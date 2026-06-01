pipeline {
  agent any

  parameters {
    choice(name: 'LIFECYCLE_OPERATION', choices: ['install', 'update', 'uninstall', 'delete'], description: 'Cloudify lifecycle operation')
    string(name: 'REQUEST_FILE', defaultValue: 'requests/hello-dev-install.yaml', description: 'Lifecycle request YAML')
  }

  environment {
    CFY_MANAGER_URL = credentials('CFY_MANAGER_URL')
    CFY_USERNAME    = credentials('CFY_USERNAME')
    CFY_PASSWORD    = credentials('CFY_PASSWORD')
    CFY_TENANT      = credentials('CFY_TENANT')
    CFY_API_VERSION = 'v3.1'
    CFY_INSECURE    = 'true'
  }

  stages {
    stage('Checkout') {
      steps { checkout scm }
    }

    stage('Prepare Python') {
      steps {
        sh '''
          set -euo pipefail
          python3 -m venv .venv
          . .venv/bin/activate
          pip install --upgrade pip
          pip install -r requirements.txt
        '''
      }
    }

    stage('Invoke Cloudify Lifecycle') {
      steps {
        sh '''
          set -euo pipefail
          . .venv/bin/activate

          case "${LIFECYCLE_OPERATION}" in
            install)   REQ="requests/hello-dev-install.yaml" ;;
            update)    REQ="requests/hello-dev-update.yaml" ;;
            uninstall) REQ="requests/hello-dev-uninstall.yaml" ;;
            delete)    REQ="${REQUEST_FILE}" ;;
            *)         REQ="${REQUEST_FILE}" ;;
          esac

          python3 scripts/cloudify_lifecycle.py --request "${REQ}"
        '''
      }
    }
  }

  post {
    always {
      archiveArtifacts artifacts: 'requests/*.yaml', fingerprint: true
    }
  }
}
