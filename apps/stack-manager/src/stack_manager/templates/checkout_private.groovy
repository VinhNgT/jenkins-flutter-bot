        // Checkout from a private repository using Jenkins credentials.
        // The credentialsId must match a credential configured in
        // Jenkins > Manage Jenkins > Credentials.
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
