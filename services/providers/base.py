class MonitoringProvider:
    data_mode = "live"
    default_vm = "randomforest-vm"
    vm_ids = ()

    def get_overview(self, vm=None, window_seconds=None):
        raise NotImplementedError(
            "Provider harus mengimplementasikan get_overview(vm, window_seconds)"
        )

    def get_detection_logs(self, limit=400):
        raise NotImplementedError(
            "Provider harus mengimplementasikan get_detection_logs(limit)"
        )

    def count_attacks(self, src_ip, since=None):
        raise NotImplementedError(
            "Provider harus mengimplementasikan count_attacks(src_ip, since)"
        )
