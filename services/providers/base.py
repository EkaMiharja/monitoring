class MonitoringProvider:
    data_mode = "live"

    def get_overview(self):
        raise NotImplementedError("Provider harus mengimplementasikan get_overview()")
