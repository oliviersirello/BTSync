""" 
Copyright 2015 Benjamin Alt 
benjaminalt@arcor.de
    
This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>. 

"""

from __future__ import division
import PyOBEX.client
import PyOBEX.responses
import BTDeviceFinder
import re
import os
import datetime
import string

filelist = []
current_path = ""
folder_path = ""

def find_target_folder(client, target_path):
    folderlist = []
    if target_path:
        folderlist = target_path.split("/")
    elif "\\" in target_path or (len(target_path) == 0):
        print "Please use forward slashes in the path declaration or enter a valid path.\n"
        print "Provision of a non-existing target directory will create it in the specified\n"
        print "location, provided the location exists."
        print "Disconnecting..."
        if isinstance(client.disconnect(), PyOBEX.responses.Success):
            print "Disconnected successfully."
        else:
            print "Disconnection failed."
        return
    target = folderlist[len(folderlist)-1]
    headers, contents = client.listdir()
    move_up(client, contents) # move all the way to highest possible directory
    headers, contents = client.listdir()
    current_folders = make_folder_list(contents)
    browse(client, target, folderlist, current_folders) # move down to target directory

def make_folder_list(contents):
    folders = []
    regex = re.compile(r'folder name=".*?"', re.UNICODE)
    temp = regex.findall(contents)
    for item in temp:
        item = re.sub('folder name="', "", item)
        item = item.rstrip('"')
        folders.append(item)
    return folders

def move_up(client, contents):
    headers, newcont = client.listdir()
    if contents == newcont:
        return
    else:
        client.setpath(to_parent = True)
        move_up(client, newcont)

def browse(client, target, folderlist, current_folders):
    count = 0
    while count < (len(folderlist) - 1):
        client.setpath(folderlist[count])
        headers, contents = client.listdir()
        current_folders = make_folder_list(contents)
        count += 1
    headers, contents = client.listdir()
    current_folders = make_folder_list(contents)
    if target in current_folders:
        client.setpath(target)
        print "Directory found."
    else:
        client.setpath(target, create_dir = True)
        print "Directory not found. New directory created at the desired location."

def one_way_sync(client, path, target_path):
    global filelist
    folderlist = target_path.split("/")
    target = folderlist[len(folderlist) - 1]
    client.setpath(to_parent = True)
    client.put("debug.txt", "debug")
    client.delete("debug.txt")
    client.delete(target)
    client.setpath(target, create_dir = True) # I am in empty target directory
    make_filelist(path) # Makes a list of files in local directory
    for item in filelist:
        temp = item
        # Remove everything before and including the local directory
        item = item.replace(path + "\\", "")
        # Turn path into list
        itemlist = item.split("\\")
        itemlist.append(temp)
        item = itemlist
        # Fill target directory on device
        index = len(item) - 2
        for i in range(0, index): # Go to place
            client.setpath(item[i], create_dir = True)
        client.put(item[index], get_data(item[index + 1]))
        for i in range (0, index): # Go back to root
            client.setpath(to_parent = True)
    filelist = []
    client.setpath(to_parent = True)

def two_way_sync(client, path):
    client.put("debug.txt", "debug")
    client.delete("debug.txt")
    recursive_two_way(client, path)

def recursive_two_way(client, path):
    global current_path
    remote_files = get_attributes_target(client)
    if current_path == "":
        present_files = get_attributes_home(path)
    else:
        present_files = get_attributes_home(os.path.join(os.path.normpath(path), current_path))
    for object in remote_files:
        print "Syncing {0}: {1}".format(object["type"], object["name"])
        # Is there an equivalent on the local machine?
        local_equiv = {}
        for item in present_files:
            if item["name"] == object["name"]:
                local_equiv = item
        if not local_equiv:
            # No equivalent on local machine --> get file/folder from remote device
            # If it is a file...
            if object["type"] == "file":
                if current_path == "":
                    whereto = os.path.join(path, object["name"])
                else:
                    whereto = os.path.join(path, current_path, object["name"])
                headers, file = client.get(object["name"])
                fo = open(whereto, mode = "wb")
                fo.write(file)
                fo.close()
            # If it is a folder...
            if object["type"] == "folder":
                if current_path != "":
                    current_path = os.path.join(current_path, object["name"])
                else: 
                    current_path = object["name"]
                client.setpath(object["name"]) # Go into the folder
                os.mkdir(os.path.join(path, current_path))
                get_folder(client, os.path.join(path, current_path), "")
                client.setpath(to_parent = True) # Go out of folder
                cutoff = current_path.rfind('\\')
                if cutoff != -1:
                    current_path = current_path[:cutoff]
                else: 
                    current_path = ""
        if local_equiv:
            # If is file: Check date
            if object["type"] == "file":
                if current_path != "":
                    whereto = os.path.join(path, current_path, object["name"])
                else:
                    whereto = os.path.join(path, object["name"])
                # If it is newer: Delete & get
                if object["date"] > local_equiv["date"]:
                    headers, file = client.get(object["name"])
                    if is_text(file):
                        fo = open(whereto, mode = "w")
                        fo.write(file)
                        fo.close()
                    else:
                        fo = open(whereto, mode = "wb")
                        fo.write(file)
                        fo.close()
                # If it is older: Delete & put
                elif object["date"] < local_equiv["date"]:
                    fo = open(whereto, mode = "rb")
                    file = fo.read()
                    fo.close()
                    client.delete(object["name"])
                    client.put(local_equiv["name"], file)
            # If is folder: go to deeper level, recurse
            elif object["type"] == "folder":
                if len(current_path) > 0:
                    current_path = os.path.join(current_path, object["name"])
                else: current_path = object["name"]
                client.setpath(object["name"])
                recursive_two_way(client, path)
    for object in present_files:
        print "Syncing {0}: {1}".format(object["type"], object["name"])
        # Is there an equivalent on the remote device?
        remote_equiv = {}
        for item in remote_files:
            if item["name"] == object["name"]:
                remote_equiv = item
        if not remote_equiv:
            # No equivalent on remote machine --> put file/folder to remote device
            if len(current_path) > 0:
                whereto = os.path.join(path, current_path, object["name"])
            else:
                whereto = os.path.join(path, object["name"])
            # If it is a file...
            if object["type"] == "file":
                fo = open(whereto, "rb")
                file = fo.read()
                fo.close()
                client.put(object["name"], file)
            # If it is a folder...
            elif object["type"] == "folder":
                if current_path == "":
                    whereto = os.path.join(path, object["name"]) # Path on the local device to the folder
                else:
                    whereto = os.path.join(path, current_path, object["name"]) # Path on the local device to the folder
                client.setpath(object["name"], create_dir = True)
                one_way_sync(client, whereto, object["name"])
    # Done with the current level
    if len(current_path):
        client.setpath(to_parent = True) # Go out of folder
        cutoff = current_path.rfind('\\')
        if cutoff != -1:
            current_path = current_path[:cutoff]
        else: 
            current_path = ""
    return

def get_folder(client, path, folder_path): # Path is path *including* directory on *home* device
    headers, data = client.listdir()
    if not data:
        return
    else:
        target_things = get_attributes_target(client)
        for item in target_things:
            if item["type"] == "file":
                headers, file = client.get(item["name"])
                fo = open(os.path.join(path, folder_path, item["name"]), "wb")
                fo.write(file)
                fo.close()
            elif item["type"] == "folder":
                newpath = os.path.join(folder_path, item["name"])
                client.setpath(item["name"])
                os.mkdir(os.path.join(path, newpath))
                get_folder(client, path, newpath)
                client.setpath(to_parent = True)

def get_data(path):
    if istext(path):
        fo = open(os.path.normpath(path), "r")
        return fo.read()
    else:
        fo = open(os.path.normpath(path), "rb")
        return fo.read()

def make_filelist(path):
    for item in os.listdir(path):
        object = os.path.join(path, item)
        if os.path.isfile(object):
            filelist.append(object)
        if os.path.isdir(object):
            make_filelist(object)

# Returns list of dicts with objects' attributes (type, name, date) in the current folder on the target device
def get_attributes_target(client):
    headers, data = client.listdir()
    files_and_folders = data.splitlines()
    if "<parent-folder/>" in files_and_folders:
        files_and_folders = files_and_folders[4:len(files_and_folders)-1]
    else:
        files_and_folders = files_and_folders[3:len(files_and_folders)-1]
    datalist = []
    folder_re = re.compile(r'folder name=".*?"', re.UNICODE)
    file_re = re.compile(r'file name=".*?"', re.UNICODE)
    datetime_re = re.compile(r'modified=".*?"', re.UNICODE)
    for item in files_and_folders:
        tempdict = {}
        tempdict["type"] = "folder" if re.findall(folder_re, item) else "file"
        if tempdict["type"] == "folder":
            tempdict["name"] = re.sub('folder name="', '', re.findall(folder_re, item)[0]).rstrip('"')
        elif tempdict["type"] == "file":
            tempdict["name"] = re.sub('file name="', '', re.findall(file_re, item)[0]).rstrip('"')
        else:
            return 
        temptime = re.sub('modified="','', re.findall(datetime_re, item)[0]).rstrip('"').replace("T", "").replace("Z", "")
        tempdict["date"] = datetime.datetime.strptime(temptime, "%Y%m%d%H%M%S").replace(second = 0)
        datalist.append(tempdict)
    return datalist

# Returns a list of dicts with objects' attributes (type, name, date) in the current folder on the home device
def get_attributes_home(path):
    files_and_folders = os.listdir(path)
    datalist = []
    for item in files_and_folders:
        tempdict = {}
        tempdict["name"] = item;
        item = os.path.join(path, item)
        tempdict["type"] = "folder" if os.path.isdir(item) else "file"
        tempdict["date"] = datetime.datetime.fromtimestamp(os.path.getmtime(item)).replace(second = 0, microsecond = 0)
        datalist.append(tempdict)
    return datalist

def istext(filename):
    s=open(filename).read(512)
    text_characters = "".join(map(chr, range(32, 127)) + list("\n\r\t\b"))
    _null_trans = string.maketrans("", "")
    if not s:
        # Empty files are considered text
        return True
    if "\0" in s:
        # Files with null bytes are likely binary
        return False
    # Get the non-text characters (maps a character to itself then
    # use the 'remove' option to get rid of the text characters.)
    t = s.translate(_null_trans, text_characters)
    # If more than 30% non-text characters, then
    # this is considered a binary file
    if float(len(t))/float(len(s)) > 0.30:
        return False
    return True

def is_text(input):
    text_characters = "".join(map(chr, range(32, 127)) + list("\n\r\t\b"))
    _null_trans = string.maketrans("", "")
    if not input:
        # Empty files are considered text
        return True
    if "\0" in input:
        # Files with null bytes are likely binary
        return False
    # Get the non-text characters (maps a character to itself then
    # use the 'remove' option to get rid of the text characters.)
    t = input.translate(_null_trans, text_characters)
    # If more than 30% non-text characters, then
    # this is considered a binary file
    if float(len(t))/float(len(input)) > 0.30:
        return False
    return True

# test client
if __name__ == "__main__":
    name = "Benjamin Alt's LG-D415"
    address = BTDeviceFinder.find_by_name(name)
    port = BTDeviceFinder.find_obex_port(address)
    client = PyOBEX.client.BrowserClient(address, port)
    client.connect()
    client.setpath("Internal storage")
    client.setpath("test")
    two_way_sync(client, r"C:\Users\Benjamin Alt\Desktop")
    client.disconnect()