import puyapy as pup
from puyapy import arc4

FOR_SALE_MBR = 2_500 + 64 * 400


class DigitalMarketplace(arc4.ARC4Contract):
    @arc4.abimethod
    def allow_asset(
        self, mbr_pay: pup.gtxn.PaymentTransaction, asset: pup.Asset
    ) -> None:
        _balance, opted_into = pup.op.AssetHoldingGet.asset_balance(
            pup.Global.current_application_address, asset.asset_id
        )
        assert not opted_into

        assert mbr_pay.receiver == pup.Global.current_application_address
        assert mbr_pay.amount == pup.Global.asset_opt_in_min_balance

        pup.itxn.AssetTransfer(
            xfer_asset=asset,
            asset_receiver=pup.Global.current_application_address,
            asset_amount=0,
        ).submit()

    @arc4.abimethod
    def first_deposit(
        self,
        mbr_pay: pup.gtxn.PaymentTransaction,
        xfer: pup.gtxn.AssetTransferTransaction,
        nonce: arc4.UInt64,
        unitary_price: arc4.UInt64,
    ) -> None:
        assert mbr_pay.sender == pup.Txn.sender
        assert mbr_pay.receiver == pup.Global.current_application_address
        assert mbr_pay.amount == FOR_SALE_MBR

        box_key = (
            pup.Txn.sender.bytes + pup.op.itob(xfer.xfer_asset.asset_id) + nonce.bytes
        )
        _length, exists = pup.op.Box.length(box_key)
        assert not exists

        assert xfer.sender == pup.Txn.sender
        assert xfer.asset_receiver == pup.Global.current_application_address
        assert xfer.asset_amount > 0

        pup.op.Box.put(box_key, pup.op.itob(xfer.asset_amount) + unitary_price.bytes)

    @arc4.abimethod
    def deposit(
        self, xfer: pup.gtxn.AssetTransferTransaction, nonce: arc4.UInt64
    ) -> None:
        box_key = (
            pup.Txn.sender.bytes + pup.op.itob(xfer.xfer_asset.asset_id) + nonce.bytes
        )
        _length, exists = pup.op.Box.length(box_key)
        assert exists

        assert xfer.sender == pup.Txn.sender
        assert xfer.asset_receiver == pup.Global.current_application_address
        assert xfer.asset_amount > 0

        current_deposited = pup.op.btoi(pup.op.Box.extract(box_key, 0, 8))
        pup.op.Box.replace(
            box_key, 0, pup.op.itob(current_deposited + xfer.asset_amount)
        )

    @arc4.abimethod
    def set_price(
        self, asset: pup.UInt64, nonce: arc4.UInt64, unitary_price: arc4.UInt64
    ) -> None:
        box_key = pup.Txn.sender.bytes + pup.op.itob(asset) + nonce.bytes

        pup.op.Box.replace(box_key, 8, unitary_price.bytes)

    @arc4.abimethod
    def withdraw(self, asset: pup.Asset, nonce: arc4.UInt64) -> None:
        box_key = pup.Txn.sender.bytes + pup.op.itob(asset.asset_id) + nonce.bytes

        current_deposited = pup.op.btoi(pup.op.Box.extract(box_key, 0, 8))
        _deleted = pup.op.Box.delete(box_key)

        pup.itxn.Payment(receiver=pup.Txn.sender, amount=FOR_SALE_MBR).submit()

        pup.itxn.AssetTransfer(
            xfer_asset=asset,
            asset_receiver=pup.Txn.sender,
            asset_amount=current_deposited,
        ).submit()

    @arc4.abimethod
    def buy(
        self,
        owner: arc4.Address,
        asset: pup.Asset,
        nonce: arc4.UInt64,
        buy_pay: pup.gtxn.PaymentTransaction,
        quantity: arc4.UInt64,
    ) -> None:
        box_key = owner.bytes + pup.op.itob(asset.asset_id) + nonce.bytes

        current_unitary_price = pup.op.btoi(pup.op.Box.extract(box_key, 8, 8))
        amount_not_scaled_high, amount_not_scaled_low = pup.op.mulw(
            current_unitary_price, quantity.decode()
        )
        scaling_factor_high, scaling_factor_low = pup.op.expw(10, asset.decimals)
        _quotient_high, amount_to_be_paid, _remainder_high, _remainder_low = (
            pup.op.divmodw(
                amount_not_scaled_high,
                amount_not_scaled_low,
                scaling_factor_high,
                scaling_factor_low,
            )
        )
        assert not _quotient_high

        assert buy_pay.sender == pup.Txn.sender
        assert buy_pay.receiver.bytes == owner.bytes
        assert buy_pay.amount == amount_to_be_paid

        current_deposited = pup.op.btoi(pup.op.Box.extract(box_key, 0, 8))
        pup.op.Box.replace(
            box_key, 0, pup.op.itob(current_deposited - quantity.decode())
        )

        pup.itxn.AssetTransfer(
            xfer_asset=asset,
            asset_receiver=pup.Txn.sender,
            asset_amount=quantity.decode(),
        ).submit()
