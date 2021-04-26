print({k: ktor.globals.common[k] for k in dir(ktor.globals.common)})

ktor.kops.cluster_name = "dev.kliasco.com"
ktor.kops.state_store = "s3://state.dev.kliasco.com"

ktor.kops.update()
