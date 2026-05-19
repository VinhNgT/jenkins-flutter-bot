// ═══════════════════════════════════════════════════════════════════════════
// Jenkins Flutter Bot — CI/CD Pipeline
// ═══════════════════════════════════════════════════════════════════════════
//
// Auto-generated Jenkinsfile for the Flutter build pipeline.
// This pipeline is designed to work with the jenkins-flutter-bot stack:
//   https://github.com/VinhNgT/jenkins-flutter-bot
//
// HOW IT WORKS:
//   1. The build-manager triggers this pipeline via Jenkins REST API
//   2. The pipeline checks out the Flutter project and builds a release APK
//   3. The APK is archived as a Jenkins artifact
//   4. Build-manager polls the Jenkins API for completion, then downloads
//      the archived artifact — no outbound HTTP from the agent
//
// AGENT REQUIREMENT:
//   Requires a Jenkins node labeled 'flutter' with Flutter + Android SDKs.
//
// ═══════════════════════════════════════════════════════════════════════════

pipeline {
    agent { label 'flutter' }

    parameters {
        // Branch to build — injected by the Telegram bot's /build command
        string(name: 'BRANCH', defaultValue: 'main')

        // Internal parameter — injected automatically by the build-manager
        // when it triggers a build.  Do NOT set this manually.
        //   BUILD_REQUEST_ID : correlation ID to match this build back to
        //                      the originating request
        string(name: 'BUILD_REQUEST_ID', defaultValue: '')
    }

    stages {
$checkout

        stage('Build APK') {
            steps {
                sh 'flutter pub get'
                sh 'flutter build apk --release'
            }
        }
    }

    post {
        success {
            archiveArtifacts artifacts: 'build/app/outputs/flutter-apk/*.apk'
        }
    }
}
