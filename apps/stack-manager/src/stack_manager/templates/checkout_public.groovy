        // Checkout from a public repository (no credentials needed).
        stage('Clone') {
            steps {
                git branch: "${params.BRANCH}",
                    url: '$repo_url'
            }
        }
