import platform

import socket

import os

import urllib.request

import shutil

import psutil

import re

ops = platform.system() #The operating system

print("The operating system on this machine is: "+platform.platform()) #Showing OS details

hostname=socket.gethostname() #Hostname is required to get the local IPv4

ipaddr=socket.gethostbyname(hostname) #The local IPv4

print("The local IP address of this machine is: "+str(ipaddr))

print("The Default Gateway of this machine is: ")

res = ipaddr.split('.') #Splitting the IP with '.' dilimiter

res2 = [eval(i) for i in res]

netip = [str(res2[0])+"."+str(res2[1])] #Connectiong the first 2 octates of the ip

if ops == "Windows":

    os.system('ipconfig | findstr "Gateway" | findstr '+str(netip[0])) #Using the first 2 octates of the ip for findstr to get the relvent gateway (only for windows)

if ops == "Linux":

    aa = os.system("ip r | grep 'default gateway' | awk '{print $3}' ")

external_ip = urllib.request.urlopen('https://ifconfig.me/').read().decode('utf8') #Getting the Public IPv4 from an external website and decoding it using UTF8

hdd = shutil.disk_usage('C:') #Checking the space of C: drive

print("The size of your hdd is: "+str(hdd.total // (2 ** 30))+"GB")

print("The size of your hdd is: "+str(hdd.used // (2 ** 30))+"GB")

print("The size of your hdd is: "+str(hdd.free // (2 ** 30))+"GB")

Mydir = os.getcwd() #Getting the current working directory

Indir = os.listdir(Mydir) #Listing the items within the directory

def get_size(start_path = '.'): #Getting the size of a directory - function imported from - https://stackoverflow.com/questions/1392413/calculating-a-directorys-size-using-python
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(start_path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            if not os.path.islink(fp):
                total_size += os.path.getsize(fp)

    return (total_size // (2**20)) #Converting the bytes into MB

a = []
for i in Indir: # a loop of the list of the names of the items within the directory tree
    s = get_size(i)
    a.append(i)
    a.append(s)

aa = []

for i in range(len(a)):

    aa.append(str(a[i]))

ab = []

for i in range(0 , len(aa) , 2):

    ab.append(aa[i]+" "+aa[i+1]+" MB")

ptrn = re.compile(r".*\s(\d+)\s*MB\s*$") #Regex to get the number before the MB

ab.sort(key=lambda x: int(ptrn.search(x).group(1)), reverse=True) #Sorting the list with size of the number before MB

print("The top 5 folders in your directory and their size are : ")

for i in range(0,5):

   print(ab[i])


print("The CPU usage is: "+str(psutil.cpu_percent())+"%")

while True:

    print("The CPU usage is: "+str(psutil.cpu_percent(10))+"%")

