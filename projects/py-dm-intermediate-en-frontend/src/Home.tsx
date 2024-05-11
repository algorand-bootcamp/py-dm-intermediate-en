// src/components/Home.tsx
import { Config as AlgokitConfig } from '@algorandfoundation/algokit-utils'
import AlgorandClient from '@algorandfoundation/algokit-utils/types/algorand-client'
import { useWallet } from '@txnlab/use-wallet'
import { decodeUint64, encodeAddress } from 'algosdk'
import React, { useEffect, useState } from 'react'
import ConnectWallet from './components/ConnectWallet'
import MethodCall from './components/MethodCall'
import { DigitalMarketplaceClient } from './contracts/DigitalMarketplace'
import * as methods from './methods'
import { getAlgodConfigFromViteEnvironment } from './utils/network/getAlgoClientConfigs'

interface HomeProps {}

const Home: React.FC<HomeProps> = () => {
  AlgokitConfig.configure({ populateAppCallResources: true })

  const [openWalletModal, setOpenWalletModal] = useState<boolean>(false)
  const [appId, setAppId] = useState<number>(0)
  const [amountToSell, setAmountToSell] = useState<bigint>(0n)
  const [sellingPrice, setSellingPrice] = useState<bigint>(0n)
  const [listings, setListings] = useState<{ seller: string; assetId: bigint; nonce: bigint; amount: bigint; unitaryPrice: bigint }[]>([])
  const [newListing, setNewListing] = useState<boolean>(false)
  const [sellerAddress, setSellerAddress] = useState<string>('')
  const [assetToBuy, setAssetToBuy] = useState<bigint>(0n)
  const [buyingNonce, setBuyingNonce] = useState<bigint>(0n)
  const [buyingPrice, setBuyingPrice] = useState<bigint>(0n)
  const [buyingQuantity, setBuyingQuantity] = useState<bigint>(0n)
  const { activeAddress, signer } = useWallet()

  useEffect(() => {
    algorand.client.algod
      .getApplicationBoxes(appId)
      .do()
      .then((boxesResponse) => {
        boxesResponse.boxes.forEach((box) => {
          algorand.client.algod
            .getApplicationBoxByName(appId, box.name)
            .do()
            .then((boxContent) => {
              setListings([
                ...listings,
                {
                  seller: encodeAddress(box.name.slice(0, 32)),
                  assetId: decodeUint64(box.name.slice(32, 40), 'bigint'),
                  nonce: decodeUint64(box.name.slice(40, 48), 'bigint'),
                  amount: decodeUint64(boxContent.value.slice(0, 8), 'bigint'),
                  unitaryPrice: decodeUint64(boxContent.value.slice(8, 16), 'bigint'),
                },
              ])
            })
        })
      })
      .catch(() => {
        setListings([])
      })

    setNewListing(false)
  }, [appId, newListing])

  const algodConfig = getAlgodConfigFromViteEnvironment()
  const algorand = AlgorandClient.fromConfig({ algodConfig })
  algorand.setDefaultSigner(signer)

  const dmClient = new DigitalMarketplaceClient(
    {
      resolveBy: 'id',
      id: appId,
      sender: { addr: activeAddress!, signer },
    },
    algorand.client.algod,
  )

  const toggleWalletModal = () => {
    setOpenWalletModal(!openWalletModal)
  }

  return (
    <div className="hero min-h-screen bg-teal-400">
      <div className="hero-content text-center rounded-lg p-6 max-w-md bg-white mx-auto">
        <div className="max-w-md">
          <h1 className="text-4xl">
            Welcome to <div className="font-bold">AlgoKit 🙂</div>
          </h1>
          <p className="py-6">
            This starter has been generated using official AlgoKit React template. Refer to the resource below for next steps.
          </p>

          <div className="grid">
            <button data-test-id="connect-wallet" className="btn m-2" onClick={toggleWalletModal}>
              Wallet Connection
            </button>

            <div className="divider" />

            <label className="label">App ID</label>
            <input
              type="number"
              className="input input-bordered m-2"
              value={appId}
              onChange={(e) => setAppId(e.currentTarget.valueAsNumber || 0)}
            />

            {activeAddress && appId === 0 && (
              <div>
                <MethodCall methodFunction={methods.create(algorand, dmClient, activeAddress, setAppId)} text="Create Marketplace" />
              </div>
            )}

            <div className="divider" />

            {activeAddress && appId !== 0 && (
              <div>
                <label className="label">Amount To Sell</label>
                <input
                  type="text"
                  className="input input-bordered"
                  value={amountToSell.toString()}
                  onChange={(e) => setAmountToSell(BigInt(e.currentTarget.value || 0))}
                />
                <label className="label">Selling Price</label>
                <input
                  type="text"
                  className="input input-bordered"
                  value={sellingPrice.toString()}
                  onChange={(e) => setSellingPrice(BigInt(e.currentTarget.value || 0))}
                />
                <MethodCall
                  methodFunction={methods.sell(algorand, dmClient, activeAddress, amountToSell, sellingPrice, setNewListing)}
                  text="Sell a new asset"
                />
              </div>
            )}

            <div className="divider" />

            <div>
              <label className="label">Listings</label>
              {appId !== 0 && (
                <ul>
                  {listings.map((listing) => (
                    <li
                      key={listing.seller + listing.assetId + listing.nonce}
                    >{`assetId: ${listing.assetId}\namount: ${listing.amount}\nprice: ${listing.unitaryPrice}`}</li>
                  ))}
                </ul>
              )}
            </div>

            <div className="divider" />

            {activeAddress && appId !== 0 && (
              <div>
                <label className="label">Seller</label>
                <input
                  type="text"
                  className="input input-bordered"
                  value={sellerAddress}
                  onChange={(e) => setSellerAddress(e.currentTarget.value)}
                />
                <label className="label">Asset To Buy</label>
                <input
                  type="text"
                  className="input input-bordered"
                  value={assetToBuy.toString()}
                  onChange={(e) => setAssetToBuy(BigInt(e.currentTarget.value || 0))}
                />
                <label className="label">Nonce</label>
                <input
                  type="text"
                  className="input input-bordered"
                  value={buyingNonce.toString()}
                  onChange={(e) => setBuyingNonce(BigInt(e.currentTarget.value || 0))}
                />
                <label className="label">Price Per Unit</label>
                <input
                  type="text"
                  className="input input-bordered"
                  value={buyingPrice.toString()}
                  onChange={(e) => setBuyingPrice(BigInt(e.currentTarget.value || 0))}
                />
                <label className="label">Desired Quantity</label>
                <input
                  type="number"
                  className="input input-bordered"
                  value={buyingQuantity.toString()}
                  onChange={(e) => setBuyingQuantity(BigInt(e.currentTarget.value || 0))}
                />
                <MethodCall
                  methodFunction={methods.buy(
                    algorand,
                    dmClient,
                    activeAddress,
                    sellerAddress,
                    assetToBuy,
                    buyingNonce,
                    buyingQuantity,
                    buyingPrice,
                    setNewListing,
                  )}
                  text={`Buy ${buyingQuantity} unit for ${buyingPrice * BigInt(buyingQuantity)} microALGO`}
                />
              </div>
            )}

            {/*{activeAddress !== seller && appId !== 0 && unitsLeft === 0n && (*/}
            {/*  <button className="btn btn-disabled m-2" disabled={true}>*/}
            {/*    SOLD OUT!*/}
            {/*  </button>*/}
            {/*)}*/}

            {/*{activeAddress === seller && appId !== 0 && unitsLeft === 0n && (*/}
            {/*  <MethodCall methodFunction={methods.deleteApp(dmClient, setAppId)} text="Delete App"/>*/}
            {/*)}*/}
          </div>

          <ConnectWallet openModal={openWalletModal} closeModal={toggleWalletModal} />
        </div>
      </div>
    </div>
  )
}

export default Home
