# Jenkins Launcher

[![Build Status](https://travis-ci.org/ocaballeror/jenkins-launch.svg?branch=master)](https://travis-ci.org/ocaballeror/jenkins-launch)

Script to launch a Jenkins build and wait for it to finish.

## Execution

##### Build output
When the build finishes, the script will fetch the Jenkins output and save it to a file in the current directory. You can use the `--dump` flag to dump it to stdout instead.

##### Build parameters
If your build takes parameters, you can pass them to the script as a list of `key=value` pairs at the end of the command.

##### Arguments
* `-j / --job`
    * Description: The URL of the jenkins job to launch
    * Required: yes
    * Example: `http://your.jenkins.example.com:8080/job/folder/job/jenkins-launcher/job/branch/`
* `-u / --user`
    * Description: The username for the Jenkins instance
    * Required: yes
    * Example: `username`
* `-t / --token`
    * Description: The authentication token for this user
    * Required: yes
    * Example: `11c2e50143bd0ae499984c7d3b07fcb7e4`
* `-q / --quiet`
    * Description: Do not print user messages
    * Required: no
* `--dump`
    * Description: Dump build output to stdout instead of saving to a file
    * Required: no
* `-l / --launch-only`
    * Description: Only launch the new job and exist when it starts running
	* Conflicts: `-w`
* `-w / --wait-only`
    * Description: Wait until the running build pointed at by `-j` finishes running
	* Conflicts: `-l`

## Examples

```sh
# Basic build launch
python launch_jenkins.py -j 'http://your.jenkins.instance:8080/job/whatever/job/master' -u username -t token

# Launch build with parameters
python launch_jenkins.py -j 'http://your.jenkins.instance:8080/job/whatever/job/master' -u username -t token param1=value 'param2=another value'

# Script-ready execution. Prints no user messages, and dumps the job output to stdout
python launch_jenkins.py -q --dump -j 'http://your.jenkins.instance:8080/job/whatever/job/master' -u username -t token param1=value param2=another_value

# Only launch the job and exit when it starts executing. The only output is the URL of the running build.
python launch_jenkins.py -q --launch-only -j http://your.jenkins.instance:8080/job/whatever/job/master -u ...
http://your.jenkins.instance:8080/job/whatever/job/master/

# Wait for a running build to finish and get its output. Note that the url corresponds to a specific build (number 62)
python launch_jenkins.py -q --wait-only --dump -j http://your.jenkins.instance:8080/job/whatever/job/master/62 -u ...

Obtained Jenkinsfile from 6ea258a9f90ed662a48882f9e2cee68713d053b3
Running in Durability level: MAX_SURVIVABILITY
[Pipeline] node
Running on rkalvjktrn1 in /var/lib/jenkins/workspace/G_ENV_TRNENV_jenkins-test_master
[Pipeline] {
[Pipeline] stage
[Pipeline] { (Declarative: Checkout SCM)
[Pipeline] checkout
Fetching changes from the remote Git repository
Fetching without tag...s
...
[Pipeline] }
[Pipeline] // node
[Pipeline] End of Pipeline
[Bitbucket] Notifying commit build result
Can not determine Jenkins root URL or Jenkins URL is not a valid URL regarding Bitbucket API. Commit status notifications are disabled until a root URL is configured in Jenkins global configuration.
Finished: SUCCESS
```
