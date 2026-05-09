pipeline {
    agent { label 'flutter' }

    parameters {
        string(name: 'BRANCH', defaultValue: 'main')
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
