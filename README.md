# Example execution
```
# Basic build launch
python launch_jenkins.py -j 'http://your.jenkins.instance:8080/job/whatever/job/master' -u username -t token

# Launch build with parameters
python launch_jenkins.py -j 'http://your.jenkins.instance:8080/job/whatever/job/master' -u username -t token param1=value param2=another_value

# Script-ready execution. Prints no user messages, and dumps the job output to stdout
python launch_jenkins.py -q --dump -j 'http://your.jenkins.instance:8080/job/whatever/job/master' -u username -t token param1=value param2=another_value
```
