import sys 
import os
import mmap
import re
import md5
import subprocess
import shutil
import errno
import time

NV_DATA_BYTES = 2048*1024
START_BYTES = '32'
GAP_MODEM = str(int('5c', 16))
NV_END       = '\xff'
NAME_NV_DATA = 'nv_data.bin'
NAME_CHECKSUM= 'nv_data.bin.md5'
P_NV_HEADER = re.compile(r'\xcc{' + START_BYTES +r'}.{' + GAP_MODEM + r'}\x20{4}(?P<modem>.{53})', re.DOTALL)

DEBUG = False

def debug(*args):
    if DEBUG:
        print ' '.join([repr(i) for i in args])

def info(*args):
    print ' '.join([repr(i) for i in args])

def generate_md5sum(data, salt="Samsung_Android_RIL"):
    checksum = md5.new(data)
    checksum.update(salt)
    return checksum.hexdigest()    

def is_valid_nv_data(data, modem_name):
    if not modem_name:
        debug('Modem name does not exist')
        return False
    if 'undefined' in modem_name.lower():
        debug('`undefined` in modem name')
        return False
    if not data[-1] == NV_END:
        debug("nv_data has bad ending:", repr(data[-1]))
        return False
    return True

class NvData(object):
    def __init__(self, data):
        self.modem = P_NV_HEADER.search(data)
        if self.modem:
            self.modem = self.modem.groupdict()['modem'].strip()
        self.checksum = generate_md5sum(data)
        self.data = data
        self.valid = is_valid_nv_data(data, self.modem)

    def save_data(self, path, name='nv_data.bin'):
        filename = os.path.join(path, name)
        with open(filename, 'w+b') as f:
            f.write(self.data)
            f.flush()
        os.chmod(filename, 0775)
        
    def save_checksum(self, path, name='nv_data.bin.md5'):
        filename = os.path.join(path, name)
        with open(filename, 'w') as f:
            f.write(self.checksum)
            f.flush()
        os.chmod(filename, 0775)

def recursive_remove(folder):
    for the_file in os.listdir(folder):
        file_path = os.path.join(folder, the_file)
        if os.path.isfile(file_path):
            os.unlink(file_path)

def check_and_prep_recover_dir(path, dirname='recovered_efs'):
    dirpath = os.path.join(path, dirname)
    if not os.path.exists(dirpath):
        os.mkdir(dirpath)
    elif not os.path.isdir(dirpath):
        print "Invalid directory: `{}`".format(dirpath)
        print "Remove file and try again."
        sys.exit(1)
    else:
        recursive_remove(dirpath)
    return dirpath

def read_stream(stream, start, count):
    old = stream.tell()
    stream.seek(start)
    data = stream.read(count)
    stream.seek(old)
    return data
  
def extract_nv_data(efs_dump):
    here = os.getcwd()
    recover_dir = check_and_prep_recover_dir(here)
    filename = efs_dump
    extracted = []
    with open(filename, 'r+b') as f:
        mm = mmap.mmap(f.fileno(), 0)
        count = 0
        for match in P_NV_HEADER.finditer(mm):
            start = match.start(0)
            data = read_stream(mm, start, NV_DATA_BYTES)
            nv_data = NvData(data)
            if not nv_data.valid:
                continue
            nv_data.save_data(recover_dir, name='nv_data.bin.' + str(count))
            nv_data.save_checksum(recover_dir, name='nv_data.bin.md5.' + str(count))
            extracted.append(nv_data)
            count += 1
        print "FOUND: ", count, "possible nv_data.bin"
    return extracted

def mount_loop_device(image_filename, path):
    loop = subprocess.check_output(['sudo', 'losetup', '-f']).strip()
    if subprocess.call(['sudo', 'losetup', loop, image_filename]) != 0:
        raise Exception("Failed to setup loop device")
    
    if subprocess.call(['sudo', 'mount', loop, path]) != 0:
        raise Exception("Failed to mount loop device")
    return loop
    
def unmount_loop_device(loop_path):
    if subprocess.call(['sudo', 'umount', loop_path]) != 0:
        raise Exception("Failed to unmount loop device")

    if subprocess.call(['sudo', 'losetup', '--detach', loop_path]) != 0:
        raise Exception("Failed to detach loop device")

def remove_file(path):
    try :
        os.remove(path)
    except OSError as e:
        if e.errno != errno.ENOENT:
            raise e
        
def update_default_image(nv_data, directory):
    to_remove = ['.nv_core.bak', '.nv_data.bak', 'nv_data.bin', 'nv.log', '.nv_core']
    bak_bin_path = '.nv_data.bak'

    md5ext = '.md5'
    for i in to_remove:
        path = os.path.join(directory, i)
        remove_file(path)
        remove_file(path + md5ext)

    nv_data.save_data(directory)    
    nv_data.save_checksum(directory)
    nv_data.save_data(directory, name='.nv_data.bak')
    nv_data.save_checksum(directory, name='.nv_data.bak.md5')

    with open(os.path.join(directory, 'FactoryApp/keystr'), 'w') as f:
        f.write('ON')
        f.flush()

    with open(os.path.join(directory, 'FactoryApp/factorymode'), 'w') as f:
        f.write('ON')
        f.flush()
    time.sleep(2)

def main():
    here = os.getcwd()
    mount_path = os.path.join(here, 'loop_mount')
    if not os.path.exists(mount_path):
        os.mkdir(mount_path)
    extracted = extract_nv_data(sys.argv[1])
    default_img = os.path.abspath(sys.argv[2])

    for i, nv_data in enumerate(extracted):
        image = os.path.join(here, 'updated_image_' + str(i) + '.img')
        shutil.copy(default_img, image)
        loop_path = mount_loop_device(image, mount_path)
        update_default_image(nv_data, mount_path)
        unmount_loop_device(loop_path)
if __name__ == "__main__":
    main()
