/* Node-API v1 only. Credentials come from the kernel, never JSON claims. */
#include <stdint.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>
typedef struct napi_env__ *napi_env;
typedef struct napi_value__ *napi_value;
typedef struct napi_callback_info__ *napi_callback_info;
typedef napi_value (*napi_callback)(napi_env, napi_callback_info);
extern int napi_get_cb_info(napi_env,napi_callback_info,size_t*,napi_value*,napi_value*,void**);
extern int napi_get_value_int32(napi_env,napi_value,int32_t*);
extern int napi_throw_error(napi_env,const char*,const char*);
extern int napi_create_object(napi_env,napi_value*);
extern int napi_create_uint32(napi_env,uint32_t,napi_value*);
extern int napi_create_function(napi_env,const char*,size_t,napi_callback,void*,napi_value*);
extern int napi_set_named_property(napi_env,napi_value,const char*,napi_value);
static napi_value peer(napi_env env,napi_callback_info info) {
    size_t argc=1; napi_value arg,result,value; int32_t fd=-1;
    pid_t pid=0; uid_t uid; gid_t gid; socklen_t size=sizeof(pid);
    if(napi_get_cb_info(env,info,&argc,&arg,NULL,NULL)||argc!=1||
       napi_get_value_int32(env,arg,&fd)||fd<0||
       getsockopt(fd,SOL_LOCAL,LOCAL_PEERPID,&pid,&size)||size!=sizeof(pid)||pid<1||
       getpeereid(fd,&uid,&gid)) {
        napi_throw_error(env,NULL,"UNIX_PEER_KERNEL_IDENTITY_UNAVAILABLE");return NULL;
    }
    if(napi_create_object(env,&result)||
       napi_create_uint32(env,(uint32_t)pid,&value)||napi_set_named_property(env,result,"pid",value)||
       napi_create_uint32(env,(uint32_t)uid,&value)||napi_set_named_property(env,result,"uid",value)||
       napi_create_uint32(env,(uint32_t)gid,&value)||napi_set_named_property(env,result,"gid",value)) {
        napi_throw_error(env,NULL,"UNIX_PEER_NAPI_RESULT");return NULL;
    }
    return result;
}
__attribute__((visibility("default"))) napi_value napi_register_module_v1(napi_env env,napi_value exports) {
    napi_value function;
    if(napi_create_function(env,"peer",4,peer,NULL,&function)||
       napi_set_named_property(env,exports,"peer",function))return NULL;
    return exports;
}
