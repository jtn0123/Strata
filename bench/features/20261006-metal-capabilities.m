#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
int main(void) {
    @autoreleasepool {
        id<MTLDevice> d = MTLCreateSystemDefaultDevice();
        printf("device=%s dispatch_counters=%d stage_counters=%d\n", d.name.UTF8String,
               [d supportsCounterSampling:MTLCounterSamplingPointAtDispatchBoundary],
               [d supportsCounterSampling:MTLCounterSamplingPointAtStageBoundary]);
        for (id<MTLCounterSet> s in d.counterSets) { printf("counter_set=%s\n", s.name.UTF8String); }
        [d release];
    }
}
