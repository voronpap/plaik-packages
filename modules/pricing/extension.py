from plaik_sdk import ExtensionRuntime


def register(runtime: ExtensionRuntime) -> None:
    if runtime.package_id != "pricing":
        raise ValueError("runtime package id does not match this package")

    def handle_reprice(context) -> None:
        del context

    runtime.jobs.register("pricing.reprice", handle_reprice)
