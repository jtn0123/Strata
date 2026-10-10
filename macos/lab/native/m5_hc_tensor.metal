// Experimental BF16 shared projections, inspired by MLX gemm_thin_nax.
// MLX design attribution: Copyright 2026 Apple Inc., MIT (patches/MLX-LICENSE.txt).
// Keeps F32 activations and outputs; no persistent converted weight copy.
#include <metal_stdlib>
#include <metal_tensor>
#include <MetalPerformancePrimitives/MetalPerformancePrimitives.h>
using namespace metal;

struct m5_hc_args { int k; int m; int rows; int add; };

template<int KS,int KK=0,int MM=0>
kernel void m5_hc_tensor(
    constant m5_hc_args & args [[buffer(0)]],
    device const bfloat * weights [[buffer(1)]],
    device const float * input [[buffer(2)]],
    device float * output [[buffer(3)]],
    device const float * residual [[buffer(4)]],
    uint3 group [[threadgroup_position_in_grid]],
    uint k_group [[simdgroup_index_in_threadgroup]]) {
    constexpr int R = 16, C = 16, BK = 64;
    const int k_dim=KK?KK:args.k,m_dim=MM?MM:args.m;
    using extents_t = dextents<int32_t,2>;
    using strides_t = array<int32_t,2>;
    using weights_t = tensor<device bfloat,extents_t,tensor_inline>;
    using output_t = tensor<device float,extents_t,tensor_inline>;
    constexpr auto desc = mpp::tensor_ops::matmul2d_descriptor(
        R,C,BK,false,true,false,mpp::tensor_ops::matmul2d_descriptor::mode::multiply_accumulate);
    mpp::tensor_ops::matmul2d<desc,execution_simdgroup> op;
    const int column = int(group.x)*C;
    weights_t w((device bfloat *)weights+column*k_dim,extents_t(k_dim,C),strides_t{1,k_dim});
    auto tile = w.template slice<BK,C>(0,0);
    auto a = op.template get_left_input_cooperative_tensor<float,bfloat,float>();
    auto d = op.template get_destination_cooperative_tensor<decltype(a),decltype(tile),float>();
    for (ushort i=0;i<d.get_capacity();++i) d[i]=0.0f;
    for (int k=int(k_group)*BK;k<k_dim;k+=KS*BK) {
        // Explicitly pad the short token dimension without narrowing F32 input.
        for (ushort i=0;i<a.get_capacity();++i) {
            const auto index=a.get_multidimensional_index(i);
            a[i] = index[1]<args.rows ? input[int(index[1])*k_dim+k+int(index[0])] : 0.0f;
        }
        tile=w.template slice<BK,C>(k,0);
        op.run(a,tile,d);
    }
    if constexpr (KS>1) {
        static_assert((KS-1)*R*C<=4096,"More than 16KiB scratch");
        threadgroup float partials[(KS-1)*R*C];
        using partial_t=tensor<threadgroup float,extents_t,tensor_inline>;
        if(k_group>0) {
            partial_t p(partials+(k_group-1)*R*C,extents_t(C,R),strides_t{1,C});
            d.store(p);
        }
        threadgroup_barrier(mem_flags::mem_threadgroup);
        if(k_group==0) {
            auto part=op.template get_destination_cooperative_tensor<decltype(a),decltype(tile),float>();
            for(int g=0;g<KS-1;++g) {
                partial_t p(partials+g*R*C,extents_t(C,R),strides_t{1,C});
                part.load(p);
                for(ushort i=0;i<d.get_capacity();++i) d[i]+=part[i];
            }
        }
    }
    if(k_group!=0) return;
    if(args.add) {
        for(ushort i=0;i<d.get_capacity();++i) {
            const auto index=d.get_multidimensional_index(i);
            if(index[1]<args.rows) d[i]+=residual[int(index[1])*m_dim+column+int(index[0])];
        }
    }
    output_t out(output+column,extents_t(C,args.rows),strides_t{1,m_dim});
    d.store(out);
}

#define HC_INSTANTIATE(KS) template [[host_name("m5_hc_tensor_ks" #KS)]] kernel void m5_hc_tensor<KS>(constant m5_hc_args &,device const bfloat *,device const float *,device float *,device const float *,uint3,uint);
HC_INSTANTIATE(1)
HC_INSTANTIATE(2)
HC_INSTANTIATE(4)
#define HC_EXACT(KS,K,M) template [[host_name("m5_hc_tensor_ks" #KS "_k" #K "_m" #M)]] kernel void m5_hc_tensor<KS,K,M>(constant m5_hc_args &,device const bfloat *,device const float *,device float *,device const float *,uint3,uint);
HC_EXACT(1,10240,320)
HC_EXACT(2,10240,320)
HC_EXACT(4,10240,320)
HC_EXACT(8,10240,320)
HC_EXACT(16,10240,320)
HC_EXACT(1,320,10240)
