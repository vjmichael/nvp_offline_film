/* NVP DCI-P4B-R1, independent raw XYZ12 component decoder.
 * Build against the source-pinned JasPer library, never OpenJPEG.
 * Fixed native stage grammar: -i p_NNNNNN.j2c -o jasper_NNNNNN.ppm.
 * No color management, resizing, network, or alternate path acceptance.
 */
#include <jasper/jasper.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>

static int names_ok(const char *in, const char *out) {
    size_t i;
    if (strlen(in)!=12 || strlen(out)!=17 || strncmp(in,"p_",2) ||
        strcmp(in+8,".j2c") || strncmp(out,"jasper_",7) || strcmp(out+13,".ppm") ||
        memcmp(in+2,out+7,6)) return 0;
    for(i=2;i<8;i++) if(in[i]<'0'||in[i]>'9') return 0;
    return 1;
}
static int dimensions_ok(unsigned w,unsigned h) {
    return (w==1998&&h==1080)||(w==2048&&(h==1080||h==858))||
        (w==3996&&h==2160)||(w==4096&&(h==2160||h==1716));
}
int main(int argc,char **argv) {
    jas_stream_t *in=NULL;
    jas_image_t *image=NULL;
    jas_matrix_t *rows[3]={NULL,NULL,NULL};
    FILE *out=NULL;
    unsigned w=0,h=0,x,y,c;
    int result=1, library=0, thread=0;
    long size;
    unsigned char row[4096*6];
    if(argc!=5 || strcmp(argv[1],"-i") || strcmp(argv[3],"-o") ||
        !names_ok(argv[2],argv[4])) return 2;
    /* Reject non-codestream, overbudget and output collision before native decode. */
    FILE *f=fopen(argv[2],"rb");
    if(!f) return 2;
    if(fgetc(f)!=0xff || fgetc(f)!=0x4f || fseek(f,0,SEEK_END) ||
       (size=ftell(f))<80 || size>1302083) {fclose(f);return 2;}
    fclose(f);
    jas_conf_clear();
    jas_conf_set_max_mem_usage((size_t)1024*1024*1024);
    jas_conf_set_dec_default_max_samples((size_t)4096*2160*3);
    if(jas_init_library()) goto done;
    library=1;
    if(jas_init_thread()) goto done;
    thread=1;
    in=jas_stream_fopen(argv[2],"rb");
    if(!in) goto done;
    int fmt=jas_image_strtofmt("jpc");
    if(fmt<0 || !(image=jas_image_decode(in,fmt,NULL))) goto done;
    if(jas_image_numcmpts(image)!=3) goto done;
    w=(unsigned)jas_image_cmptwidth(image,0); h=(unsigned)jas_image_cmptheight(image,0);
    if(!dimensions_ok(w,h)) goto done;
    for(c=0;c<3;c++) {
        if(jas_image_cmptwidth(image,c)!=w || jas_image_cmptheight(image,c)!=h ||
            jas_image_cmptprec(image,c)!=12 || jas_image_cmptsgnd(image,c) ||
            jas_image_cmpthstep(image,c)!=1 || jas_image_cmptvstep(image,c)!=1 ||
            jas_image_cmpttlx(image,c)!=0 || jas_image_cmpttly(image,c)!=0 ||
            !(rows[c]=jas_matrix_create(1,w))) goto done;
    }
    /* Exclusive creation; failed output is retained for protected host recovery. */
    out=fopen(argv[4],"wbx");
    if(!out || fprintf(out,"P6\n%u %u\n4095\n",w,h)<0) goto done;
    for(y=0;y<h;y++) {
        for(c=0;c<3;c++) if(jas_image_readcmpt(image,c,0,y,w,1,rows[c])) goto done;
        for(x=0;x<w;x++) for(c=0;c<3;c++) {
            int_fast32_t v=jas_matrix_get(rows[c],0,x);
            if(v<0 || v>4095) goto done;
            row[x*6+c*2]=(unsigned char)(v>>8); row[x*6+c*2+1]=(unsigned char)v;
        }
        if(fwrite(row,6,w,out)!=w) goto done;
    }
    if(fflush(out) || ferror(out)) goto done;
    result=0;
done:
    if(out && fclose(out)) result=1;
    for(c=0;c<3;c++) if(rows[c]) jas_matrix_destroy(rows[c]);
    if(image) jas_image_destroy(image);
    if(in) jas_stream_close(in);
    if(thread) jas_cleanup_thread();
    if(library) jas_cleanup_library();
    return result;
}
