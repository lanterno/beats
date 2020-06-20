# project-timer
measures the whole time spent on every project you have and helps you manage time on your projects.
#######
Commands..
### create a project.
./ptc.py createp ProjectName EstimatedTime Details  
### start a timer.
./ptc.py start ProjectName                         
### stops the timer. Note that you don't have to specify  a ProjectName here because
### we assume humans can work on only one project at a certain period of time.
./ptc.py stop                                      

# database
We're using mlab, and hosting our servers in Belgium (europe-west1).


###
Next steps:
- [ ] Create project endpoint
- [ ] Start timer on project
- [ ] End timer on project
- [ ] Check total time for day endpoint
- [ ] Add validation for multiple active timers
- [ ] Provide custom starting time
- [ ] Provide custom stopping time
- [ ] Deploy on GCC
- [ ] Testing with pytest
- [ ] Add CI
- [ ] Add CD using docker repository
- [ ] Add versioning the repo
- [ ] Think about Canary Releases
- [ ] Migrate old data
- [ ] Remove deprecated app
- [ ] DataLake and backup?
- [ ] Add console client written in bash or GoLang
- [ ] Add dashboard
- [ ] Think dashboard
- [ ] Think desktop app like upwork timer (for macos)
- [ ] Think browser plugin
- [ ] Think mobileApp (sheetu)
