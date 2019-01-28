uuid = UUID.randomUUID()
dslPodName = "contraDsl-${uuid}"
dockerRepoURL = '172.30.254.79:5000'
openshiftNamespace = 'ember-csi'
openshiftServiceAccount = 'jenkins'
ansibleExecutorTag = 'v1.1.2'
envPodName = "ember-csi-${uuid}"

def cleanup() {
  openshift.withCluster() {
    openshift.delete("pod","$envPodName")
  }
}

createDslContainers podName: dslPodName,
                    dockerRepoURL: dockerRepoURL,
                    openshiftNamespace: openshiftNamespace,
                    openshiftServiceAccount: openshiftServiceAccount,
                    ansibleExecutorTag: ansibleExecutorTag,
{
  node(dslPodName){

    stage("pre-flight"){
      deleteDir()
      checkout scm
    }

    stage("Parse Configuration"){
      parseConfig()
      echo env.configJSON
    }

    stage("Deploy Infra"){
      openshift.withCluster() {
        openshift.create(openshift.process(readFile('ci-automation/config/ember-csi-template.yaml'),"-p","PODNAME=$envPodName"))
      }
    }

    stage("Execute Tests"){

      try {

        try {
            executeTests verbose: true, vars: [ workspace: "${WORKSPACE}" ]
        } finally {
            junit 'junit.xml'
        }

        openshift.withCluster() {
          def podSelector = openshift.selector('pod',envPodName)
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
            openshift.rsync("${WORKSPACE}","$podName:/etc/systemd/system/vagrant-vm.service.d/workDir/workspace")
            openshiftExec(
              pod: podName,
              command: 'bash',
              arguments: ["-c", "cd /etc/systemd/system/vagrant-vm.service.d/ && vagrant rsync && vagrant ssh -c 'sh -x /vagrant/${WORKSPACE}/ci-automation/tests.sh'"],
            )
          }
        }
      } catch (Exception e) {
        currentBuild.result = 'FAILURE'
        cleanup()
        throw e
      }
    }
    
    stage('env-cleanup') {
      cleanup()
    }
  }
}
