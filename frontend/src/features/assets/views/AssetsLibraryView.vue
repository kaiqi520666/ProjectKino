<script setup lang="ts">
import { Images } from 'lucide-vue-next'
import WorkspacePageHeader from '@/components/workspace/WorkspacePageHeader.vue'
import AssetLibraryPanel from '../AssetLibraryPanel.vue'
import { useUserAssetsStore } from '../user-assets-store'

const userAssets = useUserAssetsStore()
</script>

<template>
  <section class="assets-page" aria-labelledby="assets-library-title">
    <WorkspacePageHeader
      title="素材库"
      title-id="assets-library-title"
      :badge="userAssets.items.length"
    >
      <template #icon><Images :size="19" :stroke-width="1.7" /></template>
    </WorkspacePageHeader>

    <div class="assets-page-content">
      <AssetLibraryPanel
        mode="manage"
        :allowed-kinds="['image', 'video', 'audio', 'text']"
        full-page
      />
    </div>
  </section>
</template>

<style scoped>
.assets-page {
  width: 100%;
  padding: 20px 24px 40px;
}

.assets-page-content {
  margin-top: 18px;
}

@media (max-width: 640px) {
  .assets-page {
    padding: 18px 16px 32px;
  }
}
</style>
