# From DESEC SMART RECON!

import json

dic_nuclei = {}

def parse():
    with open("nuclei.json") as jsonfile:
        counter = 0
        for line in jsonfile:
            content = line.rstrip('\n')
            data = json.loads(content)
            for item in data:
                dic_nuclei['template'] = data['template-id']
                try:
                    dic_nuclei['matched'] = data['matched']
                except:
                    dic_nuclei['matched'] = None
                dic_nuclei['severity'] = data['info']['severity']
                dic_nuclei['host'] = data['host']
                try:
                    dic_nuclei['ip'] = data['ip']
                except:
                    dic_nuclei['ip'] = None
                try:
                    dic_nuclei['extracted-results'] = data['extracted-results']
                except:
                    dic_nuclei['extracted-results'] = None
                try:
                    dic_nuclei['poc'] = data['curl-command']
                except:
                    dic_nuclei['poc'] = None
                try:
                    dic_nuclei['cve'] = data['info']['classification']['cve-id']
                except:
                    dic_nuclei['cve'] = None

                print(dic_nuclei)

if __name__ == '__main__':
    parse()
    print(dic_nuclei)
