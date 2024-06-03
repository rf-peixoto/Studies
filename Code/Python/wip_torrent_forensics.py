#pip install python-libtorrent

import libtorrent as lt
import time

def track_torrent(magnet_link):
    ses = lt.session()
    params = {
        'save_path': './',
        'storage_mode': lt.storage_mode_t(2),
        'paused': False,
        'auto_managed': True,
        'duplicate_is_error': True
    }
    handle = lt.add_magnet_uri(ses, magnet_link, params)

    print('Downloading metadata...')
    while not handle.has_metadata():
        time.sleep(1)
    print('Metadata downloaded.')

    torrent_info = handle.get_torrent_info()
    print('Torrent name:', torrent_info.name())

    print('\nTracking peers and seeds...\n')
    while True:
        status = handle.status()
        print('Peers:', status.num_peers)
        print('Seeds:', status.num_seeds)
        print('Download rate:', status.download_rate / 1000, 'kB/s')
        print('Upload rate:', status.upload_rate / 1000, 'kB/s')
        print('Progress:', status.progress * 100, '%')
        print('-' * 40)

        peers_info = handle.get_peer_info()
        for peer in peers_info:
            print(f'IP: {peer.ip}')
            print(f'Client: {peer.client}')
            print(f'Country: {peer.country}')
            print(f'Download speed: {peer.down_speed / 1000} kB/s')
            print(f'Upload speed: {peer.up_speed / 1000} kB/s')
            print(f'Progress: {peer.progress * 100}%')
            print(f'Connection type: {peer.connection_type}')
            print(f'Flags: {peer.flags}')
            print('-' * 20)
        
        time.sleep(5)

if __name__ == '__main__':
    magnet_link = input('Enter the magnet link: ')
    track_torrent(magnet_link)
