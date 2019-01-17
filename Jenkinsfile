dslPodName = "contraDsl-${UUID.randomUUID()}"
dockerRepoURL = '172.30.254.79:5000'
openshiftNamespace = 'ember-csi'
openshiftServiceAccount = 'jenkins'
ansibleExecutorTag = 'v1.1.2'

def clean() {
    String objectTypes="Pod"
    openshiftDeleteResourceByLabels(
        types: objectTypes,
        keys: "app",
        values: "ember-csi")
}

createDslContainers podName: dslPodName,
                    dockerRepoURL: dockerRepoURL,
                    openshiftNamespace: openshiftNamespace,
                    openshiftServiceAccount: openshiftServiceAccount,
                    ansibleExecutorTag: ansibleExecutorTag,
{
  node(dslPodName){

    stage("pre-flight"){
      clean()
      deleteDir()
      checkout scm
    }

    stage("Parse Configuration"){
      parseConfig()
      echo env.configJSON
    }

    stage("Deploy Infra"){
      openshiftCreateResource(
          yaml: readFile("ci-automation/config/ember-csi-pod.yaml"),
      )
    }

    stage("Execute Tests"){

      try {
        executeTests verbose: true, vars: [ workspace: "${WORKSPACE}" ]
      } finally {
        junit 'junit.xml'
      }

      openshift.withCluster() {
        def podSelector = openshift.selector(
          'pod',
          [app: 'ember-csi']
        )
        if (podSelector.count() > 0) {
          podSelector.untilEach {
            echo "pod: ${it.name()} ${it.object().status}"
            it.object().status.containerStatuses.every {
              pod -> pod.ready
            }
          }

          podSelector.withEach {
            def podName = it.object().metadata.name
            println("Working in pod: $podName")
            openshiftExec(
             pod: podName,
             command: 'bash',
             arguments: ["-c", "mkdir -p /etc/systemd/system/vagrant-vm.service.d/workDir/workspace"],
            )
            def response = openshift.rsync("${WORKSPACE}","$podName:/etc/systemd/system/vagrant-vm.service.d/workDir/workspace")
            openshiftExec(
             pod: podName,
             command: 'bash',
             arguments: ["-c", "cd /etc/systemd/system/vagrant-vm.service.d/ && vagrant rsync && vagrant ssh -c 'sh -x /vagrant/${WORKSPACE}/ci-automation/tests.sh'"],
            )
          }
        }
        else {
          sh 'echo no more than 0'
        }
      }
    }

    stage('Clean') {
      clean()
    }
  }
}
