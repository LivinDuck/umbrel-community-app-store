export APP_LIVINDUCK_HYDRODACTYL_DB_PASSWORD="$(derive_entropy "${app_entropy_identifier}-database-password")"
export APP_LIVINDUCK_HYDRODACTYL_DB_ROOT_PASSWORD="$(derive_entropy "${app_entropy_identifier}-database-root-password")"
export APP_LIVINDUCK_HYDRODACTYL_REDIS_PASSWORD="$(derive_entropy "${app_entropy_identifier}-redis-password")"
