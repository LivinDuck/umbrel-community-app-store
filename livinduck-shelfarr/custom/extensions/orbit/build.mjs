import {build} from 'esbuild';
await build({entryPoints:['client/main.ts'],bundle:true,minify:true,outfile:'public/search.js',alias:{'@bookorbit/types':'./client/vendor/types.ts'},define:{__VUE_OPTIONS_API__:'false',__VUE_PROD_DEVTOOLS__:'false',__VUE_PROD_HYDRATION_MISMATCH_DETAILS__:'false'}});
