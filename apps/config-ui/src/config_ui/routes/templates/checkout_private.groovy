        stage('Checkout') {
            steps {
                checkout([$class: 'GitSCM',
                    branches: [[name: "*/${params.BRANCH}"]],
                    userRemoteConfigs: [[
                        url: '$repo_url',
                        credentialsId: '$credentials_id'
                    ]]
                ])
            }
        }
