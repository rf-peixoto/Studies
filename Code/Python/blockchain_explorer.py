from bloxplorer import bitcoin_explorer

class ServerUpdate:
    def __init__(self):
        self.server_address = "ADDRESS"
        self.last_tx_value = ""

    def extract_value(self, last_tx):
        return str(dict(last_tx['vout'][0])['value'])

    def update_last_tx(self):
        try:
            history = bitcoin_explorer.addr.get_tx_history(self.server_address)
            last_tx = history.data[0]
            self.last_tx_value = self.extract_value(last_tx)
        except Exception as error:
            print(error)

