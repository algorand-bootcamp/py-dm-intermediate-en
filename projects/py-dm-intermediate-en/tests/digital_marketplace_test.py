import base64
import functools
from copy import deepcopy

import algokit_utils
import algosdk
import pytest
from algokit_utils import get_localnet_default_account
from algokit_utils.config import config
from algosdk.atomic_transaction_composer import TransactionWithSigner
from algosdk.transaction import (
    AssetCreateTxn,
    AssetTransferTxn,
    PaymentTxn,
    wait_for_confirmation,
)
from algosdk.v2client.algod import AlgodClient
from algosdk.v2client.indexer import IndexerClient

from smart_contracts.artifacts.digital_marketplace.client import (
    DigitalMarketplaceClient,
)

FOR_SALE_MBR = 2_500 + 64 * 400


@pytest.fixture(scope="session")
def test_assets_id(algod_client: AlgodClient) -> (int, int):
    account = get_localnet_default_account(algod_client)

    return (
        wait_for_confirmation(
            algod_client,
            algod_client.send_transaction(
                AssetCreateTxn(
                    sender=account.address,
                    sp=algod_client.suggested_params(),
                    total=10_000,
                    decimals=3,
                    default_frozen=False,
                ).sign(account.private_key)
            ),
        )["asset-index"],
        wait_for_confirmation(
            algod_client,
            algod_client.send_transaction(
                AssetCreateTxn(
                    sender=account.address,
                    sp=algod_client.suggested_params(),
                    total=10_000,
                    decimals=3,
                    default_frozen=False,
                ).sign(account.private_key)
            ),
        )["asset-index"],
    )


@pytest.fixture(scope="session")
def creator(algod_client: AlgodClient) -> algokit_utils.Account:
    return get_localnet_default_account(algod_client)


@pytest.fixture(scope="session")
def digital_marketplace_client(
    creator: algokit_utils.Account,
    algod_client: AlgodClient,
    indexer_client: IndexerClient,
) -> DigitalMarketplaceClient:
    config.configure(
        debug=True,
        # trace_all=True,
    )

    client = DigitalMarketplaceClient(
        algod_client,
        creator=creator,
        indexer_client=indexer_client,
    )

    # client.deploy(
    #     on_schema_break=algokit_utils.OnSchemaBreak.AppendApp,
    #     on_update=algokit_utils.OnUpdate.AppendApp,
    # )
    client.create_bare()
    algokit_utils.ensure_funded(
        algod_client,
        algokit_utils.EnsureBalanceParameters(
            account_to_fund=client.app_address, min_spending_balance_micro_algos=0
        ),
    )
    return client


def test_allow_asset(
    digital_marketplace_client: DigitalMarketplaceClient,
    creator: algokit_utils.Account,
    test_assets_id: (int, int),
) -> None:
    for asset_id in test_assets_id:
        pytest.raises(
            algosdk.error.AlgodHTTPError,
            functools.partial(
                digital_marketplace_client.algod_client.account_asset_info,
                digital_marketplace_client.app_address,
                asset_id,
            ),
        )

        sp = digital_marketplace_client.algod_client.suggested_params()
        sp_call = deepcopy(sp)
        sp_call.flat_fee = True
        sp_call.fee = 2_000

        result = digital_marketplace_client.allow_asset(
            mbr_pay=TransactionWithSigner(
                PaymentTxn(
                    sender=creator.address,
                    sp=sp,
                    receiver=digital_marketplace_client.app_address,
                    amt=100_000,
                ),
                creator.signer,
            ),
            asset=asset_id,
            transaction_parameters=algokit_utils.TransactionParameters(
                suggested_params=sp_call
            ),
        )

        assert result.confirmed_round

        assert (
            digital_marketplace_client.algod_client.account_asset_info(
                digital_marketplace_client.app_address, asset_id
            )["asset-holding"]["amount"]
            == 0
        )


def test_first_deposit(
    digital_marketplace_client: DigitalMarketplaceClient,
    creator: algokit_utils.Account,
    test_assets_id: (int, int),
) -> None:
    for asset_id in test_assets_id:
        box_key = (
            algosdk.encoding.decode_address(creator.address)
            + algosdk.encoding.encode_as_bytes(asset_id)
            + algosdk.encoding.encode_as_bytes(0)
        )

        sp = digital_marketplace_client.algod_client.suggested_params()
        sp_call = deepcopy(sp)
        sp_call.flat_fee = True
        sp_call.fee = 2_000

        result = digital_marketplace_client.first_deposit(
            mbr_pay=TransactionWithSigner(
                PaymentTxn(
                    sender=creator.address,
                    sp=sp,
                    receiver=digital_marketplace_client.app_address,
                    amt=FOR_SALE_MBR,
                ),
                creator.signer,
            ),
            xfer=TransactionWithSigner(
                AssetTransferTxn(
                    sender=creator.address,
                    sp=sp,
                    receiver=digital_marketplace_client.app_address,
                    amt=3_000,
                    index=asset_id,
                ),
                creator.signer,
            ),
            nonce=0,
            unitary_price=1_000_000,
            transaction_parameters=algokit_utils.TransactionParameters(
                boxes=[(0, box_key)]
            ),
        )

        assert result.confirmed_round

        box_content = digital_marketplace_client.algod_client.application_box_by_name(
            digital_marketplace_client.app_id,
            box_key,
        )["value"]
        decoded_box_content = base64.b64decode(box_content)
        assert int.from_bytes(decoded_box_content[:8], "big") == 3_000
        assert int.from_bytes(decoded_box_content[8:16], "big") == 1_000_000


def test_deposit(
    digital_marketplace_client: DigitalMarketplaceClient,
    creator: algokit_utils.Account,
    test_assets_id: (int, int),
) -> None:
    for asset_id in test_assets_id:
        box_key = (
            algosdk.encoding.decode_address(creator.address)
            + algosdk.encoding.encode_as_bytes(asset_id)
            + algosdk.encoding.encode_as_bytes(0)
        )

        sp = digital_marketplace_client.algod_client.suggested_params()
        sp_call = deepcopy(sp)
        sp_call.flat_fee = True
        sp_call.fee = 2_000

        result = digital_marketplace_client.deposit(
            xfer=TransactionWithSigner(
                AssetTransferTxn(
                    sender=creator.address,
                    sp=sp,
                    receiver=digital_marketplace_client.app_address,
                    amt=1_000,
                    index=asset_id,
                ),
                creator.signer,
            ),
            nonce=0,
            transaction_parameters=algokit_utils.TransactionParameters(
                boxes=[(0, box_key)]
            ),
        )

        assert result.confirmed_round

        box_content = digital_marketplace_client.algod_client.application_box_by_name(
            digital_marketplace_client.app_id,
            box_key,
        )["value"]
        decoded_box_content = base64.b64decode(box_content)
        assert int.from_bytes(decoded_box_content[:8], "big") == 4_000
        assert int.from_bytes(decoded_box_content[8:16], "big") == 1_000_000


def test_set_price(
    digital_marketplace_client: DigitalMarketplaceClient,
    creator: algokit_utils.Account,
    test_assets_id: (int, int),
) -> None:
    for asset_id, unitary_price in zip(test_assets_id, [3_200_000, 5_700_000]):
        box_key = (
            algosdk.encoding.decode_address(creator.address)
            + algosdk.encoding.encode_as_bytes(asset_id)
            + algosdk.encoding.encode_as_bytes(0)
        )

        result = digital_marketplace_client.set_price(
            asset=asset_id,
            nonce=0,
            unitary_price=unitary_price,
            transaction_parameters=algokit_utils.TransactionParameters(
                boxes=[(0, box_key)]
            ),
        )

        assert result.confirmed_round

        box_content = digital_marketplace_client.algod_client.application_box_by_name(
            digital_marketplace_client.app_id,
            box_key,
        )["value"]
        assert (
            int.from_bytes(base64.b64decode(box_content)[8:16], "big") == unitary_price
        )


def test_buy(
    digital_marketplace_client: DigitalMarketplaceClient,
    creator: algokit_utils.Account,
    test_assets_id: (int, int),
) -> None:
    buyer = algokit_utils.get_account(digital_marketplace_client.algod_client, "buyer")

    for asset_id, amount_to_pay in zip(test_assets_id, [6_793_600, 12_101_100]):
        box_key = (
            algosdk.encoding.decode_address(creator.address)
            + algosdk.encoding.encode_as_bytes(asset_id)
            + algosdk.encoding.encode_as_bytes(0)
        )

        wait_for_confirmation(
            digital_marketplace_client.algod_client,
            digital_marketplace_client.algod_client.send_transaction(
                AssetTransferTxn(
                    sender=buyer.address,
                    sp=digital_marketplace_client.algod_client.suggested_params(),
                    receiver=buyer.address,
                    amt=0,
                    index=asset_id,
                ).sign(buyer.private_key)
            ),
        )

        sp = digital_marketplace_client.algod_client.suggested_params()
        sp_call = deepcopy(sp)
        sp_call.flat_fee = True
        sp_call.fee = 2_000

        result = digital_marketplace_client.buy(
            owner=creator.address,
            asset=asset_id,
            nonce=0,
            buy_pay=TransactionWithSigner(
                PaymentTxn(
                    sender=buyer.address,
                    sp=sp,
                    receiver=creator.address,
                    amt=amount_to_pay,
                ),
                buyer.signer,
            ),
            quantity=2_123,
            transaction_parameters=algokit_utils.TransactionParameters(
                sender=buyer.address,
                signer=buyer.signer,
                boxes=[(0, box_key)],
                suggested_params=sp_call,
            ),
        )

        assert result.confirmed_round

        assert (
            digital_marketplace_client.algod_client.account_asset_info(
                buyer.address, asset_id
            )["asset-holding"]["amount"]
            == 2_123
        )


def test_withdraw(
    digital_marketplace_client: DigitalMarketplaceClient,
    creator: algokit_utils.Account,
    test_assets_id: (int, int),
) -> None:
    for asset_id in test_assets_id:
        box_key = (
            algosdk.encoding.decode_address(creator.address)
            + algosdk.encoding.encode_as_bytes(asset_id)
            + algosdk.encoding.encode_as_bytes(0)
        )

        before_call_amount = digital_marketplace_client.algod_client.account_info(
            creator.address
        )["amount"]

        sp = digital_marketplace_client.algod_client.suggested_params()
        sp.flat_fee = True
        sp.fee = 3_000
        result = digital_marketplace_client.withdraw(
            asset=asset_id,
            nonce=0,
            transaction_parameters=algokit_utils.TransactionParameters(
                boxes=[(0, box_key)], suggested_params=sp
            ),
        )

        assert result.confirmed_round

        after_call_amount = digital_marketplace_client.algod_client.account_info(
            creator.address
        )["amount"]

        assert after_call_amount - before_call_amount == FOR_SALE_MBR - 3_000
        assert (
            digital_marketplace_client.algod_client.account_asset_info(
                creator.address, asset_id
            )["asset-holding"]["amount"]
            == 7_877
        )
