// ═══════════════════════════════════════════════════════════════════════════
// Jenkins Flutter Bot — CI/CD Pipeline
// ═══════════════════════════════════════════════════════════════════════════
//
// Auto-generated Jenkinsfile for the Flutter build pipeline.
// This pipeline is designed to work with the jenkins-flutter-bot stack:
//   https://github.com/VinhNgT/jenkins-flutter-bot
//
// HOW IT WORKS:
//   1. The Telegram bot triggers this pipeline via Jenkins REST API
//   2. The pipeline checks out the Flutter project from Git
//   3. Builds a release APK
//   4. On completion, sends the result back to the bot via webhook
//
// AGENT REQUIREMENT:
//   This pipeline requires a Jenkins node with the label 'flutter'.
//   The flutter-agent container in the stack provides this automatically.
//   If using an external Jenkins, ensure a node with Flutter + Android SDKs
//   is labeled 'flutter'.
//
// ═══════════════════════════════════════════════════════════════════════════

pipeline {
    agent { label 'flutter' }

    parameters {
        // Branch to build — injected by the Telegram bot's /build command
        string(name: 'BRANCH', defaultValue: 'main')

        // Internal bot parameters — injected automatically when the bot
        // triggers a build.  Do NOT set these manually.
        //   BOT_CALLBACK_URL : webhook URL for build result notification
        //   BOT_REQUEST_ID   : unique ID to match webhook to the triggering chat
        //   BOT_JOB_ID       : build identifier for status tracking
        string(name: 'BOT_CALLBACK_URL', defaultValue: '')
        string(name: 'BOT_REQUEST_ID', defaultValue: '')
        string(name: 'BOT_JOB_ID', defaultValue: '')
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

    // ───────────────────────────────────────────────────────────────────────
    // Post-build: send results back to the Telegram bot via webhook.
    //
    // On success: POST the APK artifact + metadata (request_id, commit hash)
    // On failure: POST metadata only (request_id, commit hash, last 50 log lines)
    //
    // If BOT_CALLBACK_URL is empty (manual Jenkins trigger), no webhook is sent.
    // ───────────────────────────────────────────────────────────────────────
    post {
        success {
            script {
                if (params.BOT_CALLBACK_URL) {
                    def apkPath = 'build/app/outputs/flutter-apk/app-release.apk'
                    def commitHash = ''
                    try {
                        commitHash = sh(script: 'git rev-parse --verify HEAD', returnStdout: true).trim()
                    } catch (e) {
                        commitHash = ''
                    }
                    def metadata = groovy.json.JsonOutput.toJson([
                        request_id : params.BOT_REQUEST_ID,
                        job_id     : params.BOT_JOB_ID,
                        status     : 'success',
                        commit_hash: commitHash,
                    ])

                    sh """
                        curl -X POST "${params.BOT_CALLBACK_URL}" \\
                            -F 'metadata=${metadata}' \\
                            -F "artifact=@${apkPath}"
                    """
                }
            }
        }

        failure {
            script {
                if (params.BOT_CALLBACK_URL) {
                    def commitHash = ''
                    try {
                        commitHash = sh(script: 'git rev-parse --verify HEAD', returnStdout: true).trim()
                    } catch (e) {
                        commitHash = ''
                    }
                    def logs = currentBuild.rawBuild.getLog(50).join('\n')
                    def metadata = groovy.json.JsonOutput.toJson([
                        request_id : params.BOT_REQUEST_ID,
                        job_id     : params.BOT_JOB_ID,
                        status     : 'failure',
                        commit_hash: commitHash,
                        logs       : logs,
                    ])

                    sh """
                        curl -X POST "${params.BOT_CALLBACK_URL}" \\
                            -F 'metadata=${metadata}'
                    """
                }
            }
        }
    }
}
