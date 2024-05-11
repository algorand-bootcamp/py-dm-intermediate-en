import * as algokit from '@algorandfoundation/algokit-utils'
import { DigitalMarketplaceClient } from './contracts/DigitalMarketplace'

/**
 * Create the application and opt it into the desired asset
 */
export function create(
  algorand: algokit.AlgorandClient,
  dmClient: DigitalMarketplaceClient,
  sender: string,
  setAppId: (id: number) => void,
) {
  return async () => {
    const createResult = await dmClient.create.bare()

    await algorand.send.payment({
      sender,
      receiver: createResult.appAddress,
      amount: algokit.algos(0.1),
    })

    setAppId(Number(createResult.appId))
  }
}

export function sell(
  algorand: algokit.AlgorandClient,
  dmClient: DigitalMarketplaceClient,
  seller: string,
  amountToSell: bigint,
  unitaryPrice: bigint,
  setNewListing: (arg0: boolean) => void,
) {
  return async () => {
    const newAssetId = await algorand.send.assetCreate({
      sender: seller,
      total: amountToSell * BigInt(1e3),
      decimals: 3,
    })

    if (!newAssetId.confirmation.assetIndex) {
      throw new Error()
    }

    const { appAddress } = await dmClient.appClient.getAppReference()

    const mbrPayAllowASA = await algorand.transactions.payment({
      sender: seller,
      receiver: appAddress,
      amount: algokit.algos(0.1),
      extraFee: algokit.algos(0.001),
    })
    await dmClient.allowAsset({
      mbrPay: mbrPayAllowASA,
      asset: newAssetId.confirmation.assetIndex,
    })

    const mbrPayDeposit = await algorand.transactions.payment({
      sender: seller,
      receiver: appAddress,
      amount: algokit.algos(0.0281),
    })
    const xfer = await algorand.transactions.assetTransfer({
      sender: seller,
      assetId: BigInt(newAssetId.confirmation.assetIndex),
      amount: amountToSell * BigInt(1e3),
      receiver: appAddress,
    })

    // TODO: Split into firstDeposit + deposit.
    await dmClient.firstDeposit({
      mbrPay: mbrPayDeposit,
      xfer,
      nonce: 0,
      unitaryPrice,
    })

    setNewListing(true)
  }
}

export function buy(
  algorand: algokit.AlgorandClient,
  dmClient: DigitalMarketplaceClient,
  sender: string,
  sellerAddress: string,
  assetId: bigint,
  nonce: bigint,
  quantity: bigint,
  unitaryPrice: bigint,
  setNewListing: (arg0: boolean) => void,
) {
  return async () => {
    await algorand.send.assetOptIn({
      sender,
      assetId,
    })

    const buyerTxn = await algorand.transactions.payment({
      sender,
      receiver: sellerAddress,
      amount: algokit.microAlgos(Number(quantity * unitaryPrice) / 1e3),
      extraFee: algokit.algos(0.001),
    })

    await dmClient.buy({
      owner: sellerAddress,
      asset: assetId,
      nonce,
      buyPay: buyerTxn,
      quantity,
    })

    setNewListing(true)
  }
}

// export function deleteApp(dmClient: DigitalMarketplaceClient, setAppId: (id: number) => void) {
//   return async () => {
//     await dmClient.delete.deleteApplication({}, { sendParams: { fee: algokit.algos(0.003) } })
//     setAppId(0)
//   }
// }
