import os
import sys
# from spread import upload_to_spread_sheet
import datetime

import hug
from app.fms import FileManager
from app.p_time import Time

sys.path.append(os.path.dirname(os.path.abspath(__file__)))


@hug.get('/projects/create/', examples=['p_name=proj&details="details here.."&p_estimatedtime=44hours'])
def create_project(p_name, details='', p_estimatedtime="Unknown"):
    project = {
        'estimated time': p_estimatedtime,
        'details': details,
        'state': 'OFF',
        'total_spent_time': "0:0:0"
    }

    projects = FileManager.read('projects')
    projects.update({p_name: project})
    FileManager.update('projects', projects)

    FileManager.update('logs/{}'.format(p_name), [], mode='w')

    print('project created.')


@hug.get('/status/')
def get_status():
    settings = FileManager.read('settings')
    project_name = settings['working on']
    projects = FileManager.read('projects')
    status = projects.get(project_name)["state"]
    print('last project: {} and its status: {}'.format(project_name, status))


@hug.get('/projects/start/', examples='p_name=ptc&time=14:20:0')
def start_timer_on_project(p_name, time=None):
    if time:
        now = Time(str_time=time)
    else:
        now = Time()
    print("Time now: {}".format(now))
    # CHANGE PROJECT STATE TO ON
    projects = FileManager.read('projects')
    if not projects.get(p_name):
        print("We don't have a project with this name dear.")
        return
    projects.get(p_name)["state"] = "ON"
    FileManager.update('projects', projects)

    # START LOG TIME
    logs = FileManager.read('logs/{}'.format(p_name))
    logs.append({'start': str(now), 'end': 'Not yet.', 'date': Time.date()})
    FileManager.update('logs/{}'.format(p_name), logs)

    # put the project in workon in the settings file.
    settings = FileManager.read('settings')
    settings["working on"] = p_name
    FileManager.update('settings', settings)


@hug.get('/projects/stop/', examples='time=16:20:0')
def stop_timer_on_project(time=None):
    now = Time(str_time=time) if time else Time()
    print("stopping Time: " + str(now))
    # GET PROJECT NAME.
    settings = FileManager.read('settings')
    p_name = settings["working on"]

    # UPDATE THE LOG.
    logs = FileManager.read('logs/{}'.format(p_name))
    if logs[-1]["end"] != "Not yet.":
        print("Error. Either you don't have a running log or the program is writing on the wrong log instance.")
        return
    logs[-1]["end"] = str(now)
    FileManager.update('logs/{}'.format(p_name), logs)
    start = Time()
    start.set_string(logs[-1]["start"])
    now.minues(start)
    elapsed_time = now

    # CHANGE PROJECT STATE TO OFF.
    projects = FileManager.read('projects')
    current_project = projects.get(p_name)
    current_project["state"] = "OFF"

    # ADD THE ELAPSED TIME.
    total_time = Time(str_time=current_project["total_spent_time"])
    total_time.add_time(elapsed_time)
    print("Elapsed time: " + str(elapsed_time))
    current_project["total_spent_time"] = str(total_time)
    projects[p_name] = current_project
    FileManager.update('projects', projects)


@hug.get('/projects/')
@hug.cli()
def list_projects():
    projects = FileManager.read('projects')
    return [project for project in projects if not projects[project].get('archived')]


@hug.get('/day_time/', examples=['p_name=proj&date=2017-06-07'])
def get_time_for_certain_day(p_name, date=Time.date()):
    all_logs = FileManager.read('logs/{}'.format(p_name))
    day_logs = [log for log in all_logs if log.get('date', None) == date]
    total_time = Time(sec_time=sum([Time.log_time(log).get_seconds() for log in day_logs]))
    print(total_time)
    return str(total_time)


def get_total_time_for_project(project_name):
    all_logs = FileManager.read('logs/{}'.format(project_name))
    total_time = Time(sec_time=sum([Time.log_time(log).get_seconds() for log in all_logs]))
    average_per_log = str(total_time.hours / (len(all_logs) or 1))[:4]
    return "{} - with average per log: {} - number of logs: {}".format(total_time, average_per_log, len(all_logs))


def total_time_for_all_projects():
    print("Project: Total time")
    for project in list_projects():
        print("{}: {}".format(project, get_total_time_for_project(project)))
    total_time = None
    for project in list_projects():
        project_time = Time(sec_time=sum([Time.log_time(log).get_seconds() for log in FileManager.read('logs/{}'.format(project))]))
        if not total_time:
            total_time = project_time
        else:
            total_time.add_time(project_time)
    print("total user recorded time: {}".format(total_time))


@hug.get('/month_time/', examples=['p_name=proj&month=6&year=2017'])
def get_total_monthly_time_on_project(p_name, month=datetime.date.today().month, year=datetime.date.today().year):
    all_logs = FileManager.read('logs/{}'.format(p_name))
    month_logs = [log for log in all_logs if log.get('date', None) and
                  int(log.get('date').split('-')[1]) == month]  # filtered by month
    month_logs = [log for log in month_logs if log.get('date', None) and int(log.get('date').split('-')[0]) == year]
    total_time = Time(sec_time=sum([Time.log_time(log).get_seconds() for log in month_logs]))
    print(total_time)
    return str(total_time)


@hug.get('/sync/', examples=['p_name=proj&spreadsheet=WorkSheet&month=6'])
def sync(p_name='cube', spreadsheet='WorkSheet', month=datetime.date.month):
    all_logs = FileManager.read('logs/{}'.format(p_name))
    month_days = set([log['date'] for log in all_logs if log.get('date', None) and
                      int(log.get('date').split('-')[1]) == 6])
    cells_time = {}
    for day_date in month_days:
        cell_row = str(int(day_date.split('-')[2]) + 1)  # we start from 2 not 1
        cells_time.update(
            {cell_row: get_time_for_certain_day(p_name, date=day_date)})
    # return upload_to_spread_sheet(p_name=p_name, spreadsheet=spreadsheet, month=month, cells_time=cells_time)
    return 0


def execute_from_command_line(args):
    action = args.pop(0)
    if action == "createp":
        print("Creating project...")
        create_project(*args)

    elif action == "start":
        print("Happy coding...")
        start_timer_on_project(*args)

    elif action == "stop":
        print("Stopping timer...")
        stop_timer_on_project(*args)

    elif action == "list":
        print("your projects are: " + str(list_projects()))

    elif action == "total_time_for":
        print(get_total_time_for_project(args[0]))

    elif action == "draw":
        total_time_for_all_projects()

    elif action == "today_time_for":    
        return get_time_for_certain_day(*args)

    elif action == "yesterday_time_for":
        date = datetime.date.today() - datetime.timedelta(days=1)
        return get_time_for_certain_day(args[0], date=str(date))

    elif action == "date":
        print(Time.date())
    elif action == "month_time_for":
        try:
            month = int(args[1])
            try:
                year = int(args[2])
                return get_total_monthly_time_on_project(args[0], month, year)
            except:
                return get_total_monthly_time_on_project(args[0], month)

        except:
            return get_total_monthly_time_on_project(args[0])

    elif action == "sync":
        return sync()

    elif action == "status":
        return get_status()
    else:
        print("Wrong Command")


if __name__ == "__main__":
    list_projects.interface.cli()
