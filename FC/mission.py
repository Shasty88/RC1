from dronekit import connect, Command, LocationGlobal, VehicleMode, LocationGlobalRelative
import dronekit as dk
from pymavlink import mavutil
import time,sys,argparse,math
import logging
import dronekit_sitl
import dronekit

# heavyily influenced by https://github.com/dronekit/dronekit-python/blob/master/examples/mission_import_export/mission_import_export.py
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger('drone script')
parser = argparse.ArgumentParser(description='Demonstrates mission import/export from a file.')
parser.add_argument('-s', action='store_true',
                   help="Flag to start simulated vehicle")
args = parser.parse_args()

sitl=None
def initvehicle():
    if args.s:
        sitl = dronekit_sitl.SITL()
        #default = dronekit_sitl.SITL() # load a binary path (optional)
        sitl.download("plane", "3.3.0", verbose=True)
        launchargs = []#'--home=38.7874145508,-77.2792434692,100.0,1,']
        sitl.launch(launchargs, verbose=True, await_ready=True, restart=True)
        #sitl.block_until_ready(verbose=True) # explicitly wait until receiving commands
        #connection_string = sitl.connection_string()
        connection_string='127.0.0.1:14550'
        key = raw_input("connect to: "+connection_string+"?")
        if key != "y":
            exit(1)
    else:
        connection_string = '/dev/ttyS0'
    arglist = ['parameters','gps_0','armed','mode','attitude','system_status','location']
    startime = time.time()
    log.info ("Connecting")
    vehicle= dk.connect(connection_string, wait_ready = arglist, heartbeat_timeout = 300, baud = 57600)
    log.info("Time to connection: %s" % str(time.time()-startime))

    arm_and_takeoff(vehicle, 200)
    return vehicle


def readmission(aFileName):
    """
    Load a mission from a file into a list. The mission definition is in the Waypoint file
    format (http://qgroundcontrol.org/mavlink/waypoint_protocol#waypoint_file_format).
    This function is used by upload_mission().
    """
    print("\nReading mission from file: %s" % aFileName)
    cmds = vehicle.commands
    missionlist=[]
    with open(aFileName) as f:
        for i, line in enumerate(f):
            if i==0:
                if not line.startswith('QGC WPL 110'):
                    raise Exception('File is not supported WP version')
            else:
                linearray=line.split('\t')
                ln_index=int(linearray[0])
                ln_currentwp=int(linearray[1])
                ln_frame=int(linearray[2])
                ln_command=int(linearray[3])
                ln_param1=float(linearray[4])
                ln_param2=float(linearray[5])
                ln_param3=float(linearray[6])
                ln_param4=float(linearray[7])
                ln_param5=float(linearray[8])
                ln_param6=float(linearray[9])
                ln_param7=float(linearray[10])
                ln_autocontinue=int(linearray[11].strip())
                cmd = Command( 0, 0, 0, ln_frame, ln_command, ln_currentwp, ln_autocontinue, ln_param1, ln_param2, ln_param3, ln_param4, ln_param5, ln_param6, ln_param7)
                missionlist.append(cmd)
    return missionlist


def upload_mission(aFileName):
    """
    Upload a mission from a file.
    """
    #Read mission from file
    missionlist = readmission(aFileName)

    print("\nUpload mission from a file: %s" % aFileName)
    #Clear existing mission from vehicle
    print(' Clear mission')
    cmds = vehicle.commands
    cmds.clear()
    #Add new mission to vehicle
    for command in missionlist:
        cmds.add(command)
    print(' Uploading mission')
    vehicle.commands.upload()
    print('done uploading')


def download_mission():
    """
    Downloads the current mission and returns it in a list.
    It is used in save_mission() to get the file information to save.
    """
    print(" Download mission from vehicle")
    missionlist=[]
    cmds = vehicle.commands
    cmds.download()
    cmds.wait_ready()
    for cmd in cmds:
        missionlist.append(cmd)
    return missionlist

def save_mission(aFileName):
    """
    Save a mission in the Waypoint file format
    (http://qgroundcontrol.org/mavlink/waypoint_protocol#waypoint_file_format).
    """
    print("\nSave mission from Vehicle to file: %s" % aFileName)
    #Download mission from vehicle
    missionlist = download_mission()
    #Add file-format information
    output='QGC WPL 110\n'
    #Add home location as 0th waypoint
    home = vehicle.home_location
    output+="%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n" % (0,1,0,16,0,0,0,0,home.lat,home.lon,home.alt,1)
    #Add commands
    for cmd in missionlist:
        commandline="%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n" % (cmd.seq,cmd.current,cmd.frame,cmd.command,cmd.param1,cmd.param2,cmd.param3,cmd.param4,cmd.x,cmd.y,cmd.z,cmd.autocontinue)
        output+=commandline
    with open(aFileName, 'w') as file_:
        print(" Write mission to file")
        file_.write(output)


def printfile(aFileName):
    """
    Print a mission file to demonstrate "round trip"
    """
    print("\nMission file: %s" % aFileName)
    with open(aFileName) as f:
        for line in f:
            print(' %s' % line.strip())

def loiter_upload_mission(aFileName):
    vehicle.mode = VehicleMode("LOITER")
    # NOTE: automatic reindexing on upload
    log.info("Confirm Loitering: %s" % vehicle.mode)
    upload_mission(aFileName)
    vehicle.mode = VehicleMode("AUTO")
    log.info("Confirm Autopilot: %s" % vehicle.mode.name)
    log.info("Flying new mission")

def arm_and_takeoff(vehicle, aTargetAltitude):
    """
    Arms vehicle and fly to aTargetAltitude.
    """
    print("Basic pre-arm checks")
    # Don't try to arm until autopilot is ready
    while not vehicle.is_armable:
        print(" Waiting for vehicle to initialise...")
        time.sleep(1)

    print("Arming motors")
    # Copter should arm in GUIDED mode
    vehicle.mode = VehicleMode("GUIDED")
    vehicle.armed = True

    # Confirm vehicle armed before attempting to take off
    while not vehicle.armed:
        print(" Waiting for arming...")
        time.sleep(1)

    print("Taking off!")
    vehicle.simple_takeoff(aTargetAltitude)  # Take off to target altitude

    # Wait until the vehicle reaches a safe height before processing the goto
    #  (otherwise the command after Vehicle.simple_takeoff will execute
    #   immediately).
    while True:
        print(" Altitude: ", vehicle.location.global_relative_frame.alt)
        # Break and return from function just below target altitude.
        if vehicle.location.global_relative_frame.alt >= aTargetAltitude * 0.95:
            print("Reached target altitude")
            break
        time.sleep(1)






mission1in = 'mission.waypoints'
mission1out = 'exportedmission.waypoints'
mission2in = 'mission2.waypoints'
mission2out ='exportedmission2.waypoints'

vehicle = initvehicle()
vehicle.block_until_ready(verbose=True)

print("Set default/target airspeed to 3")
vehicle.airspeed = 3

print("Autopilot Firmware version: %s" % vehicle.version)
time.sleep(10)

upload_mission(mission1in)
save_mission(mission1out)

#loiter_upload_mission(mission2in)
#save_mission_mission(mission2out)

#Close vehicle object before exiting script
print("Close vehicle object")
vehicle.close()

# Shut down simulator if it was started.
if sitl is not None:
    sitl.stop()


#print("\nShow original and uploaded/downloaded files:")
#Print original file (for demo purposes only)
#printfile(import_mission_filename)
#Print exported file (for demo purposes only)
#printfile(export_mission_filename)

print('done')
