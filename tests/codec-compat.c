#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "obfuscation.h"
static void reference(uint8_t *p,int n,const char *key,int klen) {
    uint8_t crc=0;
    for(int i=0;i<n;i++) {
        uint8_t in=(uint8_t)(key[i%klen]+n+klen);
        for(int bit=0;bit<8;bit++) {
            uint8_t mix=(crc^in)&1;crc>>=1;
            if(mix)crc^=0x8c;
            in>>=1;
        }
        p[i]^=crc;
    }
}
int main(int argc,char **argv) {
    char *key=argc>1?argv[1]:"compatibility-key";
    uint8_t *a=malloc(65536),*b=malloc(65536);if(!a||!b)return 2;
    int checked=0;
    for(int pass=0;pass<3;pass++)for(int j=0;j<2304;j++) {
        int n=j<2048?j+1:4096+(j-2048)*239;
        if(pass==1)n=(j*701)%2048+1;
        if(n>65507)n=65507;
        for(int i=0;i<n;i++)a[i]=b[i]=(uint8_t)(i*17+j*31+pass);
        reference(a,n,key,strlen(key));xor_data(b,n,key,strlen(key));
        if(memcmp(a,b,n)){fprintf(stderr,"mismatch length=%d pass=%d\n",n,pass);return 1;}
        xor_data(b,n,key,strlen(key));
        for(int i=0;i<n;i++)if(b[i]!=(uint8_t)(i*17+j*31+pass))return 1;
        checked++;
    }
    printf("CODEC_BYTE_COMPATIBILITY_OK cases=%d\n",checked);free(a);free(b);return 0;
}
