class MonitoringProvider:
    data_mode = "live"
    default_vm = "randomforest-vm"
    vm_ids = ()

    def get_overview(self, vm=None, window_seconds=None):
        raise NotImplementedError(
            "Provider harus mengimplementasikan get_overview(vm, window_seconds)"
        )
