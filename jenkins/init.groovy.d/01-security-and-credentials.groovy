import jenkins.model.*
import hudson.security.*
import com.cloudbees.plugins.credentials.*
import com.cloudbees.plugins.credentials.domains.*
import com.cloudbees.plugins.credentials.impl.StringCredentialsImpl
import hudson.util.Secret

// Disable first-time setup wizard and create a simple local admin user.
def instance = Jenkins.get()

def adminUser = System.getenv('JENKINS_ADMIN_ID') ?: 'admin'
def adminPassword = System.getenv('JENKINS_ADMIN_PASSWORD') ?: 'admin123'

def realm = new HudsonPrivateSecurityRealm(false)
if (realm.getUser(adminUser) == null) {
    realm.createAccount(adminUser, adminPassword)
}
instance.setSecurityRealm(realm)

// Full control once logged in. This is for local demo/E2E lab usage.
def strategy = new FullControlOnceLoggedInAuthorizationStrategy()
strategy.setAllowAnonymousRead(false)
instance.setAuthorizationStrategy(strategy)
instance.save()

// Store Cloudify connection values as Jenkins string credentials.
def store = SystemCredentialsProvider.getInstance().getStore()
def domain = Domain.global()

def upsertStringCredential = { String id, String description, String value ->
    if (value == null || value.trim().isEmpty()) {
        value = ''
    }
    def existing = com.cloudbees.plugins.credentials.CredentialsProvider.lookupCredentials(
        com.cloudbees.plugins.credentials.common.StandardCredentials.class,
        instance,
        null,
        null
    ).find { it.id == id }

    def credential = new StringCredentialsImpl(
        CredentialsScope.GLOBAL,
        id,
        description,
        Secret.fromString(value)
    )

    if (existing != null) {
        store.updateCredentials(domain, existing, credential)
    } else {
        store.addCredentials(domain, credential)
    }
}

upsertStringCredential('cfy-manager-url', 'Cloudify Manager URL', System.getenv('CFY_MANAGER_URL'))
upsertStringCredential('cfy-username', 'Cloudify username', System.getenv('CFY_USERNAME'))
upsertStringCredential('cfy-password', 'Cloudify password', System.getenv('CFY_PASSWORD'))
upsertStringCredential('cfy-tenant', 'Cloudify tenant', System.getenv('CFY_TENANT') ?: 'default_tenant')
upsertStringCredential('cfy-api-version', 'Cloudify API version', System.getenv('CFY_API_VERSION') ?: 'v3.1')
upsertStringCredential('cfy-insecure', 'Skip TLS verification for lab/self-signed certs', System.getenv('CFY_INSECURE') ?: 'true')

SystemCredentialsProvider.getInstance().save()
