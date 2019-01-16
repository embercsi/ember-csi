dslPodName = "contraDsl-${UUID.randomUUID()}"
dockerRepoURL = '172.30.254.79:5000'
openshiftNamespace = 'ember-csi'
openshiftServiceAccount = 'jenkins'
ansibleExecutorTag = 'v1.1.2'

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
      openshiftCreateResource(
          yaml: readFile("ci-automation/config/ember-csi-image.yaml"),
          verbose: true
      )
      openshiftBuild(buildConfig: 'ember-csi', showBuildLogs: 'true')

      openshiftCreateResource(
          yaml: readFile("ci-automation/config/ember-csi-pod.yaml"),
          verbose: true
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
            it.object().status.containerStatuses.every { cont ->
              cont.ready
            }
          }
          podSelector.withEach {
            def podName = it.object().metadata.name
            println("Working in pod: $podName")
            def response = openshift.rsync("${WORKSPACE}","$podName:/etc/systemd/system/vagrant-vm.service.d/workDir")
            openshiftExec(
             pod: podName,
             command: 'bash',
             arguments: ["-c", "cd /etc/systemd/system/vagrant-vm.service.d/ && vagrant rsync && vagrant ssh -c 'sh -x /vagrant/workDir/PR_submitted_CI_ci-automation-2/ci-automation/tests.sh'"],
            )
          }
        }
        else {
          sh 'echo no more than 0'
        }
      }
    }

    stage('Clean') {
      String objectTypes="ImageStream,Build,BuildConfig,Pod"
      openshiftDeleteResourceByLabels(
          types: objectTypes,
          keys: "app",
          values: "ember-csi")
    }
  }
}
