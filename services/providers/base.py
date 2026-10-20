class MonitoringProvider:
    data_mode = "live"
    default_vm = "randomforest-vm"
    vm_ids = ()

    def get_overview(self, vm=None):
        raise NotImplementedError("Provider harus mengimplementasikan get_overview(vm)")
