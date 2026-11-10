import { registerLocalVideoStudioModule } from './local-video-studio/register';
import { registerMediaVaultModule } from './media-vault/register';
import { registerMinecraftModule } from './minecraft/register';

registerMinecraftModule();
registerMediaVaultModule();
registerLocalVideoStudioModule();
