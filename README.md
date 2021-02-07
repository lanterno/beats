# Beats
Because life is a time-series of heart beats

measures the whole time spent on every project you have and helps you manage time on your projects.

Goal: To become your time-aware assistant. *To record even your heart beats.*

---

## RoadMap:
- [x] "Create project" endpoint
- [x] Start timer on project
- [x] End timer on project
- [x] Check total time for day endpoint
- [x] Add validation for multiple active timers
- [x] Use environment variables for DB DNS
- [x] Rotate secrets
- [x] Provide custom starting time
- [x] Provide custom stopping time
- [x] Testing with pytest
- [x] Add Google build CI
- [x] Make CI push images to GCR
- [x] Remove deprecated app
- [x] Deploy on GCC
- [x] Migrate old data
- [ ] Smart assistant (alexa or google for a start)
- [ ] Enhance API by providing a timer-specific API.
        
       It shouldn't be directly interfacting The timelogs
- [ ] Move GCC to euro zone to lower latency to ~ 50 ms
- [ ] Browser plugin
- [ ] Set up different databases for different environments
- [ ] Add CD using GCR
- [ ] Version the repo
- [ ] Think about Canary Releases
- [ ] DataLake and backup?
- [ ] Dashboard
- [ ] Add console client written in bash or GoLang
- [ ] Desktop app like Upwork timer (for macos)
- [ ] MobileApp (sheetu)

### database
MongoDB hosted in the cloud. 
We can add it to compose later to make it more convenient to users


### Dependencies
To install dependencies, use `make ops` to start a shell with pipenv files in sync.
After that, run the pipenv commands you need. for example, `pipenv install pytest --dev`


### Deployment
This app uses GCP for deployment.
Currently, the process is very manual though.

The manual process:
- git push will automatically create a new image on GCR
- Go to Compute Engine, and create a new machine 
- specify the image as the one we just pushed
- put the needed env variables (check the project settings.py for that)
