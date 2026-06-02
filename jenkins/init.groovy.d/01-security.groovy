import jenkins.model.*
import hudson.security.*

String adminId = System.getenv('JENKINS_ADMIN_ID') ?: 'admin'
String adminPassword = System.getenv('JENKINS_ADMIN_PASSWORD') ?: 'admin123'

def instance = Jenkins.get()

def hudsonRealm = new HudsonPrivateSecurityRealm(false)
hudsonRealm.createAccount(adminId, adminPassword)
instance.setSecurityRealm(hudsonRealm)

def strategy = new FullControlOnceLoggedInAuthorizationStrategy()
strategy.setAllowAnonymousRead(false)
instance.setAuthorizationStrategy(strategy)

instance.save()
println("Created Jenkins admin user: ${adminId}")
