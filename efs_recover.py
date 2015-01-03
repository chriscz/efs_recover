import sys 
import os
import mmap
import re
import md5

NV_DATA_BYTES = 2048*1024
START_BYTES = '32'
GAP_MODEM = str(int('5c', 16))
NV_END       = '\xff'
NAME_NV_DATA = 'nv_data.bin'
NAME_CHECKSUM= 'nv_data.bin.md5'

DEBUG = False
def debug(*args):
    if DEBUG:
        print ' '.join([repr(i) for i in args])

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

def generate_md5sum(data, salt="Samsung_Android_RIL"):
    checksum = md5.new(data)
    checksum.update(salt)
    return checksum.hexdigest()    

def is_valid_nv_data(data, modem_name):
    if 'undefined' in modem_name.lower():
        debug('`undefined` in modem name')
        return False
    if not data[-1] == NV_END:
        debug("nv_data has bad ending:", repr(data[-1]))
        return False
    return True

def read_stream(stream, start, count):
    old = stream.tell()
    stream.seek(start)
    data = stream.read(count)
    stream.seek(old)
    return data
  
def save_nv_data(data, path, suffix='', md5=True):
    nv_data = "{}.{}".format(NAME_NV_DATA, suffix)
    nv_sum = "{}.{}".format(NAME_CHECKSUM, suffix)

    nv_data = os.path.join(path, nv_data)
    nv_sum = os.path.join(path, nv_sum)
    
    with open(nv_data, 'w+b') as f:
        f.write(data)
    if md5:
        checksum = generate_md5sum(data)
        with open(nv_sum, 'w') as f:
            f.write(checksum)

def main():
    here = os.getcwd()
    recover_dir = check_and_prep_recover_dir(here)
    p_starting = re.compile(r'\xcc{' + START_BYTES +r'}.{' + GAP_MODEM + r'}\x20{4}(?P<modem>.{53})', re.DOTALL)
    filename = sys.argv[1]
    with open(filename, 'r+b') as f:
        mm = mmap.mmap(f.fileno(), 0)
        count = 0
        for match in p_starting.finditer(mm):
            modem_name = match.groupdict()['modem'].strip()
            start = match.start(0)
            # Construct the save-to path
            nv_data = read_stream(mm, start, NV_DATA_BYTES)
            if not is_valid_nv_data(nv_data, modem_name):
                continue
            save_nv_data(nv_data, recover_dir, suffix=count)
            print "MODEM: ", modem_name
            # continue from where we stopped
            count += 1
        print "FOUND: ", count, "nv_data.bin"

if __name__ == "__main__":
    main()
