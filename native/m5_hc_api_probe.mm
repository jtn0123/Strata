#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>

// Compile and execute mixed F32/BF16 cooperative TensorOps before touching an engine.
int main(int argc,char ** argv) {
    @autoreleasepool {
        if(argc!=2) return 2;
        NSError * error=nil;
        NSString * source=[NSString stringWithContentsOfFile:[NSString stringWithUTF8String:argv[1]] encoding:NSUTF8StringEncoding error:&error];
        id<MTLDevice> dev=MTLCreateSystemDefaultDevice();
        if(!source||!dev) {fprintf(stderr,"HC_API_ERROR missing source/device\n");return 1;}
        MTLCompileOptions * options=[MTLCompileOptions new];
        options.languageVersion=(MTLLanguageVersion)(4<<16);
        id<MTLLibrary> lib=[dev newLibraryWithSource:source options:options error:&error];
        if(!lib) {fprintf(stderr,"HC_API_ERROR %s\n",[[error description] UTF8String]);return 1;}
        id<MTLCommandQueue> queue=[dev newCommandQueue];
        constexpr int K=128,M=16,T=4;
        std::vector<uint16_t> weights(K*M);
        std::vector<float> input(K*T),reference(M*T),values(weights.size());
        for(int i=0;i<K*M;++i) {float v=float((i*1337)%997-498)/498.0f;uint32_t bits;memcpy(&bits,&v,4);bits+=0x7fff+((bits>>16)&1);weights[i]=bits>>16;bits=uint32_t(weights[i])<<16;memcpy(&values[i],&bits,4);}
        for(int i=0;i<K*T;++i) input[i]=float((i*137)%953-476)/476.0f;
        for(int t=0;t<T;++t) for(int m=0;m<M;++m) {double sum=0;for(int k=0;k<K;++k) sum+=double(values[m*K+k])*input[t*K+k];reference[t*M+m]=float(sum);}
        id<MTLBuffer> w=[dev newBufferWithBytes:weights.data() length:weights.size()*2 options:MTLResourceStorageModeShared];
        id<MTLBuffer> x=[dev newBufferWithBytes:input.data() length:input.size()*4 options:MTLResourceStorageModeShared];
        id<MTLBuffer> y=[dev newBufferWithLength:(M*T+32)*4 options:MTLResourceStorageModeShared];
        for(int split:{1,2,4}) {
            NSString * name=[NSString stringWithFormat:@"m5_hc_tensor_ks%d",split];
            id<MTLFunction> fn=[lib newFunctionWithName:name];
            id<MTLComputePipelineState> pipe=[dev newComputePipelineStateWithFunction:fn error:&error];
            if(!pipe) {fprintf(stderr,"HC_API_ERROR pipeline %s\n",[[error description] UTF8String]);return 1;}
            float * out=(float *)[y contents];for(int i=0;i<M*T+32;++i) out[i]=12345.0f;
            int args[]={K,M,T,0};
            id<MTLCommandBuffer> cmd=[queue commandBuffer];id<MTLComputeCommandEncoder> enc=[cmd computeCommandEncoder];
            [enc setComputePipelineState:pipe];[enc setBytes:args length:sizeof(args) atIndex:0];
            [enc setBuffer:w offset:0 atIndex:1];[enc setBuffer:x offset:0 atIndex:2];
            [enc setBuffer:y offset:16*4 atIndex:3];[enc setBuffer:y offset:16*4 atIndex:4];
            [enc dispatchThreadgroups:MTLSizeMake(1,1,1) threadsPerThreadgroup:MTLSizeMake(32,split,1)];
            [enc endEncoding];[cmd commit];[cmd waitUntilCompleted];
            if(cmd.status!=MTLCommandBufferStatusCompleted) {fprintf(stderr,"HC_API_ERROR dispatch %s\n",[[cmd.error description] UTF8String]);return 1;}
            double squared=0,denom=0,max_error=0;
            for(int i=0;i<M*T;++i) {double e=out[16+i]-reference[i];squared+=e*e;denom+=reference[i]*reference[i];max_error=fmax(max_error,fabs(e));}
            for(int i=0;i<16;++i) if(out[i]!=12345.0f||out[16+M*T+i]!=12345.0f) {fprintf(stderr,"HC_API_ERROR masked output overrun\n");return 1;}
            const double nmse=squared/denom;
            if(!std::isfinite(nmse)||nmse>1e-8||max_error>0.0001) {fprintf(stderr,"HC_API_ERROR numerical mismatch %.9g %.9g\n",nmse,max_error);return 1;}
            printf("HC_API_CHECK ks=%d nmse=%.9g max_error=%.9g passed\n",split,nmse,max_error);
        }
        puts("HC_API_DONE 3 passed");
    }
    return 0;
}
