import jenkins.model.*
import org.jenkinsci.plugins.workflow.job.WorkflowJob
import org.jenkinsci.plugins.workflow.cps.CpsFlowDefinition

Jenkins jenkins = Jenkins.get()

String defaultDeployment = System.getenv('DEFAULT_DEPLOYMENT_FILE') ?: 'deployments/wr-demo-jenkins-hello-dev.yaml'
String defaultAction = System.getenv('DEFAULT_ACTION') ?: 'create-environment'
String defaultWorkflow = System.getenv('DEFAULT_WORKFLOW') ?: 'install'
String gitRepo = System.getenv('JENKINS_GIT_REPO_URL') ?: ''
String gitBranch = System.getenv('JENKINS_GIT_BRANCH') ?: 'main'
String pollSchedule = System.getenv('JENKINS_POLL_SCHEDULE') ?: 'H/2 * * * *'

String commonEnvBlock = '''
        CFY_MANAGER_URL = "''' + (System.getenv('CFY_MANAGER_URL') ?: '') + '''"
        CFY_USERNAME = "''' + (System.getenv('CFY_USERNAME') ?: '') + '''"
        CFY_PASSWORD = "''' + (System.getenv('CFY_PASSWORD') ?: '') + '''"
        CFY_TENANT = "''' + (System.getenv('CFY_TENANT') ?: 'default_tenant') + '''"
        CFY_API_VERSION = "''' + (System.getenv('CFY_API_VERSION') ?: 'v3.1') + '''"
        CFY_INSECURE = "''' + (System.getenv('CFY_INSECURE') ?: 'true') + '''"
        GITOPS_MULTI_DEPLOYMENT_MODE = "''' + (System.getenv('GITOPS_MULTI_DEPLOYMENT_MODE') ?: 'all') + '''"
'''

String manualPipeline = '''
pipeline {
    agent any
    options { disableConcurrentBuilds(); buildDiscarder(logRotator(numToKeepStr: '20')) }
    parameters {
        string(name: 'DEPLOYMENT_FILE', defaultValue: "''' + defaultDeployment + '''", description: 'Deployment desired-state YAML')
        choice(name: 'ACTION', choices: ['create-environment', 'execute-workflow', 'delete-environment'], description: 'Cloudify action')
        string(name: 'WORKFLOW', defaultValue: "''' + defaultWorkflow + '''", description: 'Workflow for execute-workflow, e.g. install, execute_operation, heal, scale, custom workflow')
        string(name: 'PARAMETERS_FILE', defaultValue: '', description: 'Optional workflow parameters YAML, e.g. workflow-params/execute-configure.yaml')
        booleanParam(name: 'INJECT_INPUTS_AS_OPERATION_KWARGS', defaultValue: false, description: 'Inject deployment input YAML values as operation_kwargs')
    }
    environment {
''' + commonEnvBlock + '''
    }
    stages {
        stage('Use mounted envops repo') {
            steps {
                sh ''' + "'''" + '''
                    set -e
                    rm -rf "$WORKSPACE/cloudify-envops"
                    cp -R /opt/cloudify-envops "$WORKSPACE/cloudify-envops"
                    cd "$WORKSPACE/cloudify-envops"
                    python3 -m pip install -r requirements.txt --break-system-packages || python3 -m pip install -r requirements.txt
                    test -f scripts/cloudify_lifecycle.py
                    test -f scripts/manual_lifecycle_from_deployment.py
                    test -f "$DEPLOYMENT_FILE"
                ''' + "'''" + '''
            }
        }
        stage('Run Cloudify action') {
            steps {
                sh ''' + "'''" + '''
                    set -e
                    cd "$WORKSPACE/cloudify-envops"
                    EXTRA=""
                    if [ "$INJECT_INPUTS_AS_OPERATION_KWARGS" = "true" ]; then
                      EXTRA="$EXTRA --inject-inputs-as-operation-kwargs"
                    fi
                    if [ -n "$PARAMETERS_FILE" ]; then
                      EXTRA="$EXTRA --parameters-file $PARAMETERS_FILE"
                    fi
                    python3 scripts/manual_lifecycle_from_deployment.py \
                      --deployment "$DEPLOYMENT_FILE" \
                      --action "$ACTION" \
                      --workflow "$WORKFLOW" \
                      $EXTRA
                ''' + "'''" + '''
            }
        }
    }
    post {
        always {
            archiveArtifacts artifacts: 'cloudify-envops/logs/**', allowEmptyArchive: true
        }
    }
}
'''

String gitPipeline = '''
pipeline {
    agent any
    options { disableConcurrentBuilds(); buildDiscarder(logRotator(numToKeepStr: '20')) }
    triggers {
        pollSCM("''' + pollSchedule + '''")
    }
    environment {
''' + commonEnvBlock + '''
        JENKINS_GIT_REPO_URL = "''' + gitRepo + '''"
        JENKINS_GIT_BRANCH = "''' + gitBranch + '''"
    }
    stages {
        stage('Checkout envops repo') {
            steps {
                sh 'rm -rf repo'
                dir('repo') {
                    git branch: env.JENKINS_GIT_BRANCH, url: env.JENKINS_GIT_REPO_URL
                }
            }
        }
        stage('Install dependencies') {
            steps {
                dir('repo') {
                    sh 'python3 -m pip install -r requirements.txt --break-system-packages || python3 -m pip install -r requirements.txt'
                }
            }
        }
        stage('Reconcile Cloudify changes') {
            steps {
                dir('repo') {
                    sh ''' + "'''" + '''
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
                        python3 scripts/gitops_reconcile.py \
                          --before "$BEFORE" \
                          --after "$AFTER" \
                          --mode "$GITOPS_MULTI_DEPLOYMENT_MODE"
                        echo "$AFTER" > "$STATE_FILE"
                    ''' + "'''" + '''
                }
            }
        }
    }
    post {
        always {
            archiveArtifacts artifacts: 'repo/logs/**', allowEmptyArchive: true
        }
    }
}
'''

def createOrUpdateJob(String name, String script) {
    def existing = Jenkins.get().getItem(name)
    WorkflowJob job = existing instanceof WorkflowJob ? existing : Jenkins.get().createProject(WorkflowJob, name)
    job.setDefinition(new CpsFlowDefinition(script, true))
    job.save()
    println("Created/updated Jenkins pipeline job: ${name}")
}

createOrUpdateJob('cloudify-envops-manual', manualPipeline)
if ((System.getenv('ENABLE_JENKINS_GIT_JOB') ?: 'true').toBoolean()) {
    createOrUpdateJob('cloudify-envops-git-polling', gitPipeline)
}

jenkins.save()
