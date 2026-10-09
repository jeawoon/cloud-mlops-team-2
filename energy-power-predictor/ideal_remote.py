"""Read public IDEAL ZIP members using bounded HTTP ranges, not full archives."""
import io
import urllib.request
import zipfile

BASE = 'https://datashare.ed.ac.uk/server/api/core/bitstreams/'
ARCHIVES = {'household':('32316855-78ab-4279-8543-2992b12d322f',15863138394),
            'room':('b6e8483c-e5a8-4867-ba5a-1bcf0b4e96e2',10005114253)}


class RemoteFile(io.RawIOBase):
    def __init__(self, url, size):
        self.url, self.size, self.position = url, size, 0
        self.cache = None

    def seekable(self): return True
    def readable(self): return True
    def tell(self): return self.position

    def seek(self, offset, whence=0):
        self.position = offset if whence==0 else self.position+offset if whence==1 else self.size+offset
        if self.position<0: raise ValueError('Negative offset')
        return self.position

    def read(self, size=-1):
        if size<0: size=self.size-self.position
        size=min(size,self.size-self.position)
        if size<=0:return b''
        start=self.position
        if self.cache and self.cache[0]<=start and start+size<=self.cache[0]+len(self.cache[1]):
            data=self.cache[1][start-self.cache[0]:start-self.cache[0]+size]
        else:
            length=min(max(size,256*1024),self.size-start)
            request=urllib.request.Request(self.url,headers={'Range':f'bytes={start}-{start+length-1}'})
            with urllib.request.urlopen(request,timeout=45) as response:
                if response.status!=206:
                    raise RuntimeError('Server does not support ranged downloads; full download aborted')
                content_range=response.headers.get('Content-Range','')
                if not content_range.startswith(f'bytes {start}-'):
                    raise RuntimeError('Unexpected byte range')
                block=response.read(length+1)
            if len(block)!=length:raise RuntimeError('Incomplete range')
            self.cache=(start,block)
            data=block[:size]
        self.position+=len(data)
        return data


def archive(kind):
    uuid,size=ARCHIVES[kind]
    return zipfile.ZipFile(RemoteFile(BASE+uuid+'/content',size))


def download_member(zipped, name, output):
    """Download just one compressed member; zipfile validates its CRC."""
    import io
    import struct
    from pathlib import Path
    info=zipped.getinfo(name)
    remote=zipped.fp
    remote.seek(info.header_offset)
    header=remote.read(30)
    signature,*_,filename_length,extra_length=struct.unpack('<4s5H3I2H',header)
    if signature!=b'PK\x03\x04':raise ValueError('Invalid ZIP member header')
    length=30+filename_length+extra_length+info.compress_size
    remote.seek(info.header_offset)
    block=remote.read(length)
    # Recreate a tiny single-member ZIP with a correct local offset.
    import copy
    clone=copy.copy(info)
    clone.header_offset=0
    # Decompression via ZipExtFile, including original CRC verification.
    stream=zipfile.ZipExtFile(io.BytesIO(block[30+filename_length+extra_length:]),'r',clone)
    output=Path(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    with stream,output.open('wb') as handle:
        while True:
            chunk=stream.read(1024*1024)
            if not chunk:break
            handle.write(chunk)
    if output.stat().st_size!=info.file_size:raise ValueError('Member size mismatch')
    return {'file':output.name,'member':name,'zip_crc32':info.CRC,'bytes':info.file_size}


if __name__=='__main__':
    for kind in ARCHIVES:
        with archive(kind) as zipped:
            print(kind,len(zipped.infolist()),flush=True)
            for info in zipped.infolist()[:12]:
                print(info.filename,info.compress_size,info.file_size,flush=True)
