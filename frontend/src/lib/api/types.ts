import type { components as Admin } from './admin'
import type { components as Tenant } from './tenant'

export type SessionInfo = Tenant['schemas']['SessionInfo']
export type Capabilities = Tenant['schemas']['Capabilities']
export type OutletOut = Tenant['schemas']['OutletOut']
export type MfaSetupOut = Tenant['schemas']['MfaSetupOut']
export type RecoveryCodesOut = Tenant['schemas']['RecoveryCodesOut']
export type AdminSessionOut = Admin['schemas']['AdminSessionOut']
export type TenantOut = Admin['schemas']['TenantOut']
