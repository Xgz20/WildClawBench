/* Minimal stable Node-API v1 surface; no V8/Electron private ABI or application hooks. */
#include <stddef.h>
#include <stdlib.h>
#include <dlfcn.h>
typedef struct napi_env__ *napi_env;
typedef struct napi_value__ *napi_value;
typedef struct napi_callback_info__ *napi_callback_info;
typedef napi_value (*napi_callback)(napi_env, napi_callback_info);
extern int napi_get_cb_info(napi_env,napi_callback_info,size_t*,napi_value*,napi_value*,void**);
extern int napi_get_value_string_utf8(napi_env,napi_value,char*,size_t,size_t*);
extern int napi_throw_error(napi_env,const char*,const char*);
extern int napi_get_boolean(napi_env,int,napi_value*);
extern int napi_create_function(napi_env,const char*,size_t,napi_callback,void*,napi_value*);
extern int napi_set_named_property(napi_env,napi_value,const char*,napi_value);
static napi_value apply(napi_env env,napi_callback_info info) {
    size_t argc=1,length=0; napi_value arg,result;
    if(napi_get_cb_info(env,info,&argc,&arg,NULL,NULL)||argc!=1||
       napi_get_value_string_utf8(env,arg,NULL,0,&length)||length>131072) {
        napi_throw_error(env,NULL,"SEATBELT_PROFILE_ARGUMENT");return NULL;
    }
    char *profile=calloc(length+1,1),*error=NULL;
    if(!profile){napi_throw_error(env,NULL,"SEATBELT_ALLOCATION");return NULL;}
    if(napi_get_value_string_utf8(env,arg,profile,length+1,&length)) {
        free(profile);napi_throw_error(env,NULL,"SEATBELT_PROFILE_ARGUMENT");return NULL;
    }
    void *lib=dlopen("/usr/lib/libsandbox.1.dylib",RTLD_NOW|RTLD_LOCAL);
    int (*init)(const char*,unsigned long long,const char*const*,char**)=lib?dlsym(lib,"sandbox_init_with_parameters"):NULL;
    void (*free_error)(char*)=lib?dlsym(lib,"sandbox_free_error"):NULL;
    if(!init||!free_error){free(profile);napi_throw_error(env,NULL,"SEATBELT_API_UNAVAILABLE");return NULL;}
    int status=init(profile,0,NULL,&error);free(profile);
    if(status){napi_throw_error(env,NULL,error?error:"SEATBELT_APPLY_FAILED");if(error)free_error(error);return NULL;}
    napi_get_boolean(env,1,&result);return result;
}
__attribute__((visibility("default"))) napi_value napi_register_module_v1(napi_env env,napi_value exports) {
    napi_value function;
    if(napi_create_function(env,"apply",5,apply,NULL,&function)||napi_set_named_property(env,exports,"apply",function))return NULL;
    return exports;
}
