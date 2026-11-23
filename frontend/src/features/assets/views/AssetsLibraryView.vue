<script setup lang="ts">
import WorkspacePageHeader from '@/components/workspace/WorkspacePageHeader.vue'
import AssetLibraryPanel from '../AssetLibraryPanel.vue'
</script>

<template>
  <section class="assets-library-page" aria-labelledby="assets-library-title">
    <WorkspacePageHeader title-id="assets-library-title" title="素材库" />
    <AssetLibraryPanel
      mode="manage"
      :allowed-kinds="['image', 'video', 'audio', 'text']"
      full-page
    />
  </section>
</template>

<style scoped>
.assets-library-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-height: 0;
}
</style>
