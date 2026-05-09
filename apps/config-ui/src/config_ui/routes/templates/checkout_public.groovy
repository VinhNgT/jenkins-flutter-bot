        stage('Clone') {
            steps {
                git branch: "${params.BRANCH}",
                    url: '$repo_url'
            }
        }
