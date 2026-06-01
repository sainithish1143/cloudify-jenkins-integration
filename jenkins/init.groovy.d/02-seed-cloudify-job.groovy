import jenkins.model.*
import org.jenkinsci.plugins.workflow.job.WorkflowJob
import org.jenkinsci.plugins.workflow.cps.CpsFlowDefinition
import org.jenkinsci.plugins.workflow.cps.CpsScmFlowDefinition
import hudson.model.ParametersDefinitionProperty
import hudson.model.ChoiceParameterDefinition
import hudson.plugins.git.GitSCM
import hudson.plugins.git.BranchSpec
import hudson.plugins.git.UserRemoteConfig
import hudson.triggers.SCMTrigger

// Creates two Jenkins jobs:
// 1. cloudify-lifecycle-e2e: local/manual parameterized E2E job using mounted repo under /opt/cloudify-lifecycle.
// 2. cloudify-lifecycle-gitops-polling: optional Git polling job using Jenkinsfile.gitops from the configured repo.

def instance = Jenkins.get()
def defaultRequest = System.getenv('DEFAULT_REQUEST_FILE') ?: 'requests/hello-dev-install.yaml'

def requestChoices = [
    defaultRequest,
    'requests/hello-dev-install.yaml',
    'requests/hello-dev-update.yaml',
    'requests/hello-dev-uninstall.yaml'
].unique().join('\n')

// -------------------------------
// Job 1: Local/manual E2E job
// -------------------------------
def localJobName = 'cloudify-lifecycle-e2e'
def pipelineScript = '''
pipeline {
    agent any

    options {
        buildDiscarder(logRotator(numToKeepStr: '20'))
        disableConcurrentBuilds()
    }

    stages {
        stage('Validate Request') {
            steps {
                sh ''' + "'''" + '''
                    set -e
                    cd /opt/cloudify-lifecycle
                    test -f scripts/cloudify_lifecycle.py
                    test -f "${REQUEST_FILE}"
                    echo "Using request file: ${REQUEST_FILE}"
                ''' + "'''" + '''
            }
        }

        stage('Validate Cloudify Environment') {
            steps {
                sh ''' + "'''" + '''
                    set -e
                    test -n "${CFY_MANAGER_URL:-}" || { echo "CFY_MANAGER_URL is missing in .env.jenkins"; exit 1; }
                    test -n "${CFY_USERNAME:-}" || { echo "CFY_USERNAME is missing in .env.jenkins"; exit 1; }
                    test -n "${CFY_PASSWORD:-}" || { echo "CFY_PASSWORD is missing in .env.jenkins"; exit 1; }
                    test -n "${CFY_TENANT:-}" || { echo "CFY_TENANT is missing in .env.jenkins"; exit 1; }
                    echo "Cloudify environment is available for tenant: ${CFY_TENANT}"
                ''' + "'''" + '''
            }
        }

        stage('Execute Cloudify Lifecycle') {
            steps {
                sh ''' + "'''" + '''
                    set -euo pipefail
                    cd /opt/cloudify-lifecycle
                    python3 scripts/cloudify_lifecycle.py --request "${REQUEST_FILE}"
                ''' + "'''" + '''
            }
        }
    }

    post {
        success {
            echo 'Cloudify lifecycle completed successfully.'
        }
        failure {
            echo 'Cloudify lifecycle failed. Check console output for details.'
        }
    }
}
'''

def localJob = instance.getItem(localJobName)
if (localJob == null) {
    localJob = instance.createProject(WorkflowJob, localJobName)
}
localJob.setDefinition(new CpsFlowDefinition(pipelineScript, true))
localJob.setDescription('Manual E2E Jenkins job. Uses mounted local repo and runs scripts/cloudify_lifecycle.py with selected request YAML.')
localJob.removeProperty(ParametersDefinitionProperty.class)
localJob.addProperty(new ParametersDefinitionProperty(new ChoiceParameterDefinition('REQUEST_FILE', requestChoices, 'Cloudify lifecycle request YAML to execute')))
localJob.save()
println("Created/updated parameterized job: ${localJobName}")

// -------------------------------
// Job 2: Git polling job
// -------------------------------
def enableGitJob = (System.getenv('ENABLE_JENKINS_GIT_JOB') ?: 'true').toBoolean()
def repoUrl = System.getenv('JENKINS_GIT_REPO_URL') ?: ''
def branch = System.getenv('JENKINS_GIT_BRANCH') ?: 'main'
def credentialsId = System.getenv('JENKINS_GIT_CREDENTIALS_ID') ?: ''
def pollSchedule = System.getenv('JENKINS_POLL_SCHEDULE') ?: 'H/2 * * * *'

def gitJobName = 'cloudify-lifecycle-gitops-polling'
if (enableGitJob && repoUrl?.trim()) {
    def gitJob = instance.getItem(gitJobName)
    if (gitJob == null) {
        gitJob = instance.createProject(WorkflowJob, gitJobName)
    }

    def userRemoteConfigs = [new UserRemoteConfig(repoUrl, null, null, credentialsId?.trim() ? credentialsId : null)]
    def branches = [new BranchSpec("*/${branch}")]
    def scm = new GitSCM(userRemoteConfigs, branches, false, [], null, null, [])
    def flowDef = new CpsScmFlowDefinition(scm, 'Jenkinsfile.gitops')
    flowDef.setLightweight(true)
    gitJob.setDefinition(flowDef)
    gitJob.setDescription("Git-triggered Cloudify lifecycle job. Watches ${repoUrl} branch ${branch}, loads Jenkinsfile.gitops, and runs scripts/cloudify_lifecycle.py.")

    // Add SCM polling trigger. First build may need to be run once manually; after that Jenkins detects changes.
    gitJob.getTriggers().clear()
    def trigger = new SCMTrigger(pollSchedule)
    gitJob.addTrigger(trigger)
    trigger.start(gitJob, true)

    gitJob.save()
    println("Created/updated Git polling job: ${gitJobName} for ${repoUrl} branch ${branch} with schedule ${pollSchedule}")
} else {
    println("Git polling job not created. Set ENABLE_JENKINS_GIT_JOB=true and JENKINS_GIT_REPO_URL in .env.jenkins to enable it.")
}

instance.save()
