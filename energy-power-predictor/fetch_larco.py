"""Download only LARCO measured-cycle summary, not 38GB audio/vibration."""
import hashlib
import json
import struct
import urllib.request
import zlib
from pathlib import Path

ROOT=Path(__file__).parent
SOURCE='https://zenodo.org/records/18657997'
URL=SOURCE+'/files/general.zip?download=1'
SIZE=188371071


def read_summary():
    # Version-pinned ZIP central directory was inspected first. Fetch only this
    # member's local record; avoid repeating slow directory requests.
    offset,compressed=152919928,486578
    length=compressed+2048
    request=urllib.request.Request(URL,headers={'Range':f'bytes={offset}-{offset+length-1}'})
    with urllib.request.urlopen(request,timeout=30) as response:
        if response.status!=206 or not response.headers.get('Content-Range','').startswith(f'bytes {offset}-'):
            raise RuntimeError('Bounded download unsupported; full archive not downloaded')
        block=response.read(length+1)
    if len(block)!=length:raise ValueError('Incomplete member range')
    signature,version,flags,method,_,_,crc,cs,us,nl,el=struct.unpack('<4s5H3I2H',block[:30])
    name=block[30:30+nl].decode()
    if signature!=b'PK\x03\x04' or name!='aggregated_data.csv' or method!=8:
        raise ValueError('Unexpected version or ZIP member')
    start=30+nl+el
    body=zlib.decompress(block[start:start+compressed],-15)
    if flags&8:
        trailer=block[start+compressed:]
        if trailer[:4]==b'PK\x07\x08':trailer=trailer[4:]
        crc=struct.unpack('<I',trailer[:4])[0]
    if zlib.crc32(body)!=crc or len(body)!=1312274:
        raise ValueError('Member CRC or size mismatch')
    return body,crc


def main():
    folder=ROOT/'data/larco';folder.mkdir(parents=True,exist_ok=True)
    body,crc=read_summary()
    (folder/'aggregated_data.csv').write_bytes(body)
    manifest={'source':SOURCE,'license':'CC-BY-4.0',
              'license_record':'https://zenodo.org/api/records/18657997',
              'member':'aggregated_data.csv','zip_crc32':crc,
              'sha256':hashlib.sha256(body).hexdigest(),'bytes':len(body),
              'note':'Raw summary extracted without modification. Includes real measured cycle totals; not household user-intent logs.'}
    (folder/'manifest.json').write_text(json.dumps(manifest,indent=2))
    print(json.dumps(manifest),flush=True)


if __name__=='__main__':main()
